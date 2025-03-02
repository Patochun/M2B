from config.globals import *
from config.config import bDat, BlenderObjectType
from utils.collection import createCollection
from utils.object import createBlenderObject, createDuplicateLinkedObject
from utils.animation import noteAnimate
from utils.stuff import wLog, parseRangeFromTracks

"""
Creates a Geometry Nodes setup for generating sparkles cloud effect

This function creates a geometry nodes modifier that generates a cloud of sparkles
around a mesh. It uses point distribution on an icosphere to create the cloud effect.

Parameters:
    nameGN (str): Name for the geometry nodes group and modifier
    obj (bpy.types.Object): Blender object to add the modifier to
    sparklesMaterial (bpy.types.Material): Material to apply to sparkles

Node Setup:
    - Input icosphere for cloud volume
    - Point distribution for sparkle positions
    - Instance smaller icospheres as sparkles
    - Material assignment for sparkles

Inputs exposed:
    - radiusSparklesCloud: Overall cloud size (0.0-1.0)
    - radiusSparkles: Individual sparkle size (0.0-0.05)
    - densityCloud: Sparkle density (0-10)
    - densitySeed: Random seed for distribution (0-100000)
    - sparkleMaterial: Material for sparkles

Returns:
    None

Usage:
    createSparklesCloudGN("SparklesEffect", myObject, myMaterial)
"""
def createSparklesCloudGN(nameGN, obj, sparklesMaterial):
    # Add a modifier Geometry Nodes
    mod = obj.modifiers.new(name=nameGN, type='NODES')
    
    # Create a new node group
    nodeGroup = bDat.node_groups.new(name=nameGN, type="GeometryNodeTree")

    # Associate group with modifier
    mod.node_group = nodeGroup

    # Define inputs and outputs
    nodeGroup.interface.new_socket(socket_type="NodeSocketGeometry", name="Geometry", in_out="INPUT")
    socketRadiusSparklesCloud = nodeGroup.interface.new_socket(socket_type="NodeSocketFloat", name="radiusSparklesCloud", in_out="INPUT", description="Radius of the sparkles cloud")
    socketRadiusSparkles = nodeGroup.interface.new_socket(socket_type="NodeSocketFloat", name="radiusSparkles", in_out="INPUT", description="Radius of the sparkles")
    socketDensityCloud = nodeGroup.interface.new_socket(socket_type="NodeSocketFloat", name="densityCloud", in_out="INPUT", description="Density of the sparkles cloud")
    socketDensitySeed = nodeGroup.interface.new_socket(socket_type="NodeSocketInt", name="densitySeed", in_out="INPUT", description="Seed of the sparkles cloud")
    nodeGroup.interface.new_socket(socket_type="NodeSocketMaterial", name="sparkleMaterial", in_out="INPUT")
    nodeGroup.interface.new_socket(socket_type="NodeSocketGeometry", name="Geometry", in_out="OUTPUT")

    socketRadiusSparklesCloud.default_value = 1.0
    socketRadiusSparklesCloud.min_value = 0.0
    socketRadiusSparklesCloud.max_value = 1.0
    
    socketRadiusSparkles.default_value = 0.02
    socketRadiusSparkles.min_value = 0.0
    socketRadiusSparkles.max_value = 0.05
    
    socketDensityCloud.default_value = 10
    socketDensityCloud.min_value = 0
    socketDensityCloud.max_value = 10
        
    socketDensitySeed.default_value = 0
    socketDensitySeed.min_value = 0
    socketDensitySeed.max_value = 100000
    
    # Add necessary nodes
    nodeInput = nodeGroup.nodes.new("NodeGroupInput")
    nodeInput.location = (-500, 0)

    nodeOutput = nodeGroup.nodes.new("NodeGroupOutput")
    nodeOutput.location = (800, 0)

    icoSphereCloud = nodeGroup.nodes.new("GeometryNodeMeshIcoSphere")
    icoSphereCloud.location = (-300, 200)
    icoSphereCloud.inputs["Subdivisions"].default_value = 3

    multiplyNode = nodeGroup.nodes.new("ShaderNodeMath")
    multiplyNode.location = (-300, -100)
    multiplyNode.operation = 'MULTIPLY'
    multiplyNode.inputs[1].default_value = 10.0

    distributePoints = nodeGroup.nodes.new("GeometryNodeDistributePointsOnFaces")
    distributePoints.location = (0, 200)

    icoSphereSparkles = nodeGroup.nodes.new("GeometryNodeMeshIcoSphere")
    icoSphereSparkles.location = (0, -200)
    icoSphereSparkles.inputs["Subdivisions"].default_value = 1

    instanceOnPoints = nodeGroup.nodes.new("GeometryNodeInstanceOnPoints")
    instanceOnPoints.location = (300, 200)

    setMaterial = nodeGroup.nodes.new("GeometryNodeSetMaterial")
    setMaterial.location = (600, 200)
    
    # Connect nodes
    links = nodeGroup.links
    links.new(icoSphereCloud.outputs["Mesh"], distributePoints.inputs["Mesh"])
    links.new(distributePoints.outputs["Points"], instanceOnPoints.inputs["Points"])
    links.new(multiplyNode.outputs["Value"], distributePoints.inputs["Density"])
    links.new(instanceOnPoints.outputs["Instances"], setMaterial.inputs["Geometry"])
    links.new(icoSphereSparkles.outputs["Mesh"], instanceOnPoints.inputs["Instance"])
    links.new(nodeInput.outputs["radiusSparklesCloud"], icoSphereCloud.inputs["Radius"])
    links.new(nodeInput.outputs["radiusSparkles"], icoSphereSparkles.inputs["Radius"])
    links.new(nodeInput.outputs["densityCloud"], multiplyNode.inputs[0])
    links.new(nodeInput.outputs["densitySeed"], distributePoints.inputs["Seed"])
    links.new(nodeInput.outputs["sparkleMaterial"], setMaterial.inputs["Material"])
    links.new(setMaterial.outputs["Geometry"], nodeOutput.inputs["Geometry"])

    wLog(f"Geometry Nodes '{nameGN}' created successfully!")
    return


"""
Creates a fireworks visualization where notes are represented as exploding sparkle clouds.

This function creates a fireworks display where:
- Notes are arranged in a grid pattern
- Each note is represented by a sphere with sparkle particles
- Spheres explode with particles when notes are played
- Colors are assigned by track

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply ("Spread", "MultiLight", etc)

Structure:
    - FireworksV1 (main collection)
        - FW-TrackN (per track collections)
            - Sphere objects with sparkle clouds
            - Each sphere positioned by note/octave

Grid Layout:
    - X axis: Notes within octave (0-11)
    - Y axis: Octaves
    - Z axis: Animation space for explosions

Returns:
    None
"""
def createFireworksV1(trackMask, typeAnim):

    wLog(f"Create a Fireworks V1 Notes Animation type = {typeAnim}")

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tracksProcessed, tracksColor = parseRangeFromTracks(trackMask)
    tracks = glb.tracks

    # Create master BG collection
    FWCollect = createCollection("FireworksV1", glb.masterCollection)

    # Create model Sphere
    FWModelSphere = createBlenderObject(
        BlenderObjectType.ICOSPHERE,
        collection=glb.hiddenCollection,
        name="FWModelSphere",
        material=glb.matGlobalCustom,
        location=(0,0,-5),
        radius=1
    )

    # create sparklesCloudGN and set parameters
    createSparklesCloudGN("SparklesCloud", FWModelSphere, glb.matGlobalCustom)
    radiusSparklesCloud = FWModelSphere.modifiers["SparklesCloud"].node_group.interface.items_tree["radiusSparklesCloud"].identifier
    FWModelSphere.modifiers["SparklesCloud"][radiusSparklesCloud] = 1.0
    radiusSparkles = FWModelSphere.modifiers["SparklesCloud"].node_group.interface.items_tree["radiusSparkles"].identifier
    FWModelSphere.modifiers["SparklesCloud"][radiusSparkles] = 0.02
    densityCloud = FWModelSphere.modifiers["SparklesCloud"].node_group.interface.items_tree["densityCloud"].identifier
    FWModelSphere.modifiers["SparklesCloud"][densityCloud] = 0.1
    sparkleMaterial = FWModelSphere.modifiers["SparklesCloud"].node_group.interface.items_tree["sparkleMaterial"].identifier
    FWModelSphere.modifiers["SparklesCloud"][sparkleMaterial] = glb.matGlobalCustom
       
    spaceX = 5
    spaceY = 5
    offsetX = 5.5 * spaceX # center of the octave, mean between fifth and sixt note
    offsetY = (octaveCount * spaceY) - (spaceY / 2)

    # Construction
    noteCount = 0
    for trackCount, trackIndex in enumerate(listOfSelectedTrack):
        track = tracks[trackIndex]

        # create collection
        FWTrackName = f"FW-{trackIndex}-{track.name}"
        FWTrackCollect = createCollection(FWTrackName, FWCollect)

        # one sphere per note used
        for note in track.notesUsed:
            noteCount += 1
            # create sphere
            sphereName = f"Sphere-{trackIndex}-{note}"
            sphereLinked = createDuplicateLinkedObject(FWTrackCollect, FWModelSphere, sphereName, independant=False)
            sphereLinked.location = ((note % 12) * spaceX - offsetX, (note // 12) * spaceY - offsetY, 0)
            sphereLinked.scale = (0,0,0)
            sphereLinked["baseColor"] = tracksColor[trackCount]
            sphereLinked["emissionColor"] = tracksColor[trackCount]
            sparkleCloudSeed = sphereLinked.modifiers["SparklesCloud"].node_group.interface.items_tree["densitySeed"].identifier
            sphereLinked.modifiers["SparklesCloud"][sparkleCloudSeed] = noteCount

        wLog(f"Fireworks - create {noteCount} sparkles cloud for track {trackIndex} (range noteMin-noteMax) ({track.minNote}-{track.maxNote})")

    # Animation
    for trackCount, trackIndex in enumerate(listOfSelectedTrack):
        track = tracks[trackIndex]

        for noteIndex, note in enumerate(track.notes):
            # Construct the sphere name and animate
            objName = f"Sphere-{trackIndex}-{note.noteNumber}"
            noteObj = bDat.objects[objName]
            noteAnimate(noteObj, typeAnim, track, noteIndex, tracksColor[trackCount-1])

        wLog(f"Fireworks - Animate sparkles cloud for track {trackIndex} (notesCount) ({noteIndex})")

    return
