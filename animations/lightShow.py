from config.globals import *
from config.config import bDat, BlenderObjectType
from utils.collection import createCollection
from utils.object import createBlenderObject, createDuplicateLinkedObject
from utils.stuff import wLog, parseRangeFromTracks, extractOctaveAndNote
from utils.animation import distributeObjectsWithClampTo, animCircleCurve
from colorsys import hsv_to_rgb

# Return a list of color r,g,b,a dispatched
def generateHSVColors(nSeries):
    colors = []
    for i in range(nSeries):
        hue = i / nSeries  # uniform space
        saturation = 0.8    # Saturation high for vibrant color
        value = 0.9         # High luminosity
        r,g,b = hsv_to_rgb(hue, saturation, value)
        colors.append((r,g,b))
    return colors


def createLightShow(trackMask, typeAnim):

    wLog(f"Create a Light Show Notes Animation type = {typeAnim}")
    
    listOfSelectedTrack, noteMin, noteMax, octaveCount, tracksProcessed, tracksColor = parseRangeFromTracks(trackMask)
    tracks = glb.tracks
    fps = glb.fps

    # generate a track count list of dispatched colors
    randomHSVColors = generateHSVColors(len(glb.tracks))
    
    # Create master LightShow collection
    lightShowCollection = createCollection("LightShow", glb.masterCollection)
    
    ringCount = 64  # Number of rings to create
    # Create model objects
    lightShowModelUVSphere = createBlenderObject(
        BlenderObjectType.UVSPHERE,
        collection=glb.hiddenCollection,
        name="lightShowModelUVSphere",
        location=(0, 0, -5),
        radius=1,
        segments=48,
        rings=ringCount
    )

    # Create the two materials
    mat_opaque = bDat.materials.new(name="mat_opaque")
    mat_opaque.use_nodes = True
    mat_opaque.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 1.0
    
    mat_trans = bDat.materials.new(name="mat_trans")
    mat_trans.use_nodes = True
    mat_trans.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.0
    
    # Assign both materials to sphere
    lightShowModelUVSphere.data.materials.append(mat_opaque)  # Material index 0
    lightShowModelUVSphere.data.materials.append(mat_trans)   # Material index 1

    vertices_per_ring = 48  # Double the previous value
    vertices_per_octave = vertices_per_ring * 3  # 2 rings used + 1 ring skipped

    mesh = lightShowModelUVSphere.data

    # Create dictionary to store face indices per note
    note_faces = {}
    
    offset = 10  # Offset to center the rings
    # Create vertex groups and store face indices
    for octave in range(11):
        for note in range(12):
            vg = lightShowModelUVSphere.vertex_groups.new(name=f"note_{octave}-{note}")
            
            # Calculate base index and vertices
            baseIndex = 1 + ((octave+offset) * vertices_per_octave)
            v1 = baseIndex + (note * 4)
            v2 = v1 + 1
            v3 = v1 + vertices_per_ring
            v4 = v2 + vertices_per_ring
            
            # Store vertices in vertex group
            if all(v < len(mesh.vertices) for v in [v1, v2, v3, v4]):
                vg.add([v1, v2, v3, v4], 1.0, 'ADD')
                
                # Find and store face index
                for face in mesh.polygons:
                    if all(v in face.vertices for v in [v1, v2, v3, v4]):
                        note_faces[f"note_{octave}-{note}"] = face.index
                        break
                                                
    # # Verify assignments
    # for group in lightShowModelUVSphere.vertex_groups:
    #     vertices_in_group = []
    #     for v in mesh.vertices:
    #         try:
    #             group.weight(v.index)
    #             vertices_in_group.append(v.index)
    #         except RuntimeError:
    #             continue
    #     wLog(f"Group {group.name} has {len(vertices_in_group)} vertices: {vertices_in_group}")

    sphereLights = []
    # Create on sphere per track
    for trackCount, trackIndex in enumerate(listOfSelectedTrack):
        track = tracks[trackIndex]

        # Create collection for track
        trackName = f"Track-{trackIndex}-{track.name}"
        trackCollection = createCollection(trackName, lightShowCollection)

        # Create sphere object
        sphereName = f"Sphere-{trackIndex}-{track.name}"
        sphere = createDuplicateLinkedObject(trackCollection, lightShowModelUVSphere, sphereName, independant=True)
        sphere.location = (0, 0, 0)
        sphereLights.append(sphere)

        if typeAnim == "Cycle":
            # Create Light Point into sphere
            lightPoint = createBlenderObject(
                BlenderObjectType.LIGHTSHOW,
                collection=trackCollection,
                name=f"Light-{trackIndex}-{track.name}",
                location=sphere.location,
                typeLight='POINT',
                radius=0.2
            )
            lightPoint["emissionColor"] = tracksColor[trackCount]
            lightPoint["emissionStrength"] = 20000
        else:
            # Create Light Point into sphere
            lightPoint = createBlenderObject(
                BlenderObjectType.POINT,
                collection=trackCollection,
                name=f"Light-{trackIndex}-{track.name}",
                location=sphere.location,
                typeLight='POINT',
                radius=0.8
            )
            lightPoint.data.color = randomHSVColors[trackIndex]
            lightPoint.data.energy = 2000000

        # parent light to sphere
        lightPoint.parent = sphere

        # Initialize all faces to opaque at frame 0
        mesh = sphere.data
        for face in mesh.polygons:
            face.material_index = 0
            face.keyframe_insert('material_index', frame=0)
    
        # Animate the sphere
        for noteIndex, note in enumerate(track.notes):
            # Find the previous note with the same note number
            previousNote = None
            for prevIndex in range(noteIndex - 1, -1, -1):
                if track.notes[prevIndex].noteNumber == note.noteNumber:
                    previousNote = track.notes[prevIndex]
                    break

            # Find the next note with the same note number
            nextNote = None
            for nextIndex in range(noteIndex + 1, len(track.notes)):
                if track.notes[nextIndex].noteNumber == note.noteNumber:
                    nextNote = track.notes[nextIndex]
                    break

            octave, noteNumber = extractOctaveAndNote(note.noteNumber)
            noteName = f"note_{octave}-{noteNumber}"
            noteFrameOn = int(note.timeOn * fps)
            noteFrameOff = int(note.timeOff * fps)
            
            # Get face directly from stored index
            if noteName in note_faces:
                face = mesh.polygons[note_faces[noteName]]
                face.material_index = 0
                face.keyframe_insert('material_index', frame=noteFrameOn - 1)
                face.material_index = 1
                face.keyframe_insert('material_index', frame=noteFrameOn)
                face.material_index = 1
                face.keyframe_insert('material_index', frame=noteFrameOff - 1)
                face.material_index = 0
                face.keyframe_insert('material_index', frame=noteFrameOff)

        wLog(f"Light Show - Animate track {trackIndex} with {noteIndex} notes")

    # Create circle curve for trajectory of spheres
    radiusCurve = 10
    lightShowTrajectory = createBlenderObject(
        BlenderObjectType.BEZIER_CIRCLE,
        collection=lightShowCollection,
        name="lightShowTrajectory",
        location=(0, 0, 3),
        radius=radiusCurve
    )

    # spheres along the curve
    distributeObjectsWithClampTo(sphereLights, lightShowTrajectory)
    animCircleCurve(lightShowTrajectory, 0.03)
