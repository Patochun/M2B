from config.globals import *
from config.config import bDat, BlenderObjectType
from utils.collection import createCollection
from utils.object import createBlenderObject, createDuplicateLinkedObject
from utils.stuff import wLog, parseRangeFromTracks

"""
Creates a particle-based fireworks visualization using Blender's particle system.

This function creates an advanced fireworks display where:
- Notes are arranged in a 3D grid (X: notes, Y: octaves, Z: tracks)
- Each note has an emitter and sparkle objects
- Emitters shoot particles based on note timing
- Particles inherit track colors and note velocities

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply

Structure:
    - FireworksV2 (main collection)
        - FW-TrackN (per track collections)
            - Emitter spheres
            - Sparkle particles
            - Particle systems

Grid Layout:
    - X axis: Notes within octave (0-11)
    - Y axis: Octaves
    - Z axis: Track layers

Particle System:
    - Count: 100 particles per note
    - Lifetime: 50 frames
    - Velocity: Based on note velocity
    - Gravity: Reduced to 10%
    - Size variation: 20%

Returns:
    None
"""
def createFireworksV2(trackMask, typeAnim):

    wLog(f"Create a Fireworks V2 Notes Animation type = {typeAnim}")

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tracksProcessed, tracksColor = parseRangeFromTracks(trackMask)
    tracks = glb.tracks
    fps = glb.fps

    # Create master BG collection
    FWCollect = createCollection("FireworksV2", glb.masterCollection)

    # Create model objects
    FWModelEmitter = createBlenderObject(
        BlenderObjectType.ICOSPHERE,
        collection=glb.hiddenCollection,
        name="FWV2Emitter",
        material=glb.matGlobalCustom,
        location=(0,0,-5),
        radius=1
    )

    FWModelSparkle = createBlenderObject(
        BlenderObjectType.ICOSPHERE,
        collection=glb.hiddenCollection,
        name="FWV2Sparkles",
        material=glb.matGlobalCustom,
        location=(0,0,-5),
        radius=0.1
    )

    spaceX = 5
    spaceY = 5
    spaceZ = 5
    offsetX = 5.5 * spaceX # center of the octave, mean between fifth and sixt note
    octaveMin = noteMin // 12
    octaveMax = noteMax // 12
    octaveCenter = ((octaveMax - octaveMin) / 2) + octaveMin
    trackCenter = (len(tracks)-1) / 2

    # Construction
    noteCount = 0
    for trackCount, trackIndex in enumerate(listOfSelectedTrack):
        track = tracks[trackIndex]

        # create collection
        FWTrackName = f"FW-{trackIndex}-{track.name}"
        FWTrackCollect = createCollection(FWTrackName, FWCollect)

        # one sphere per note used
        for note in track.notesUsed:
            # create sphere
            pX = (note % 12) * spaceX - offsetX
            pY = ((note // 12) - octaveCenter) * spaceY
            pZ = (trackIndex - trackCenter) * spaceZ
            emitterName = f"noteEmitter-{trackIndex}-{note}"
            sphereLinked = createDuplicateLinkedObject(FWTrackCollect, FWModelEmitter, emitterName, independant=False)
            sphereLinked.location = (pX, pY, pZ)
            sphereLinked.scale = (1,1,1)
            sphereLinked["alpha"] = 0.0
            sparkleName = f"noteSparkles-{trackIndex}-{note}"
            sphereLinked = createDuplicateLinkedObject(glb.hiddenCollection, FWModelSparkle, sparkleName, independant=False)
            sphereLinked.location = (pX, pY, pZ)
            sphereLinked.scale = (1,1,1)
            sphereLinked["baseColor"] = tracksColor[trackCount]
            sphereLinked["emissionColor"] = tracksColor[trackCount]

        wLog(f"Fireworks V2 - create {len(track.notesUsed)} sparkles cloud for track {trackIndex} (range noteMin-noteMax) ({track.minNote}-{track.maxNote})")

        # create animation
        noteCount = 0
        for noteIndex, note in enumerate(track.notes):
            noteCount += 1
            
            frameTimeOn = int(note.timeOn * fps)
            frameTimeOff = int(note.timeOff * fps)

            emitterName = f"noteEmitter-{trackIndex}-{note.noteNumber}"
            emitterObj = bDat.objects[emitterName]

            # Add a particle system to the object
            psName = f"PS-{noteCount}"
            particleSystem = emitterObj.modifiers.new(name=psName, type='PARTICLE_SYSTEM')
            particleSettings = bDat.particles.new(name="ParticleSettings")

            # Assign the particle settings to the particle system
            particleSystem.particle_system.settings = particleSettings

            # Configure particle system settings
            particleSettings.count = 100  # Number of particles
            particleSettings.lifetime = 50  # Lifetime of each particle
            particleSettings.frame_start = frameTimeOn  # Start frame for particle emission
            particleSettings.frame_end = frameTimeOff  # End frame for particle emission
            particleSettings.normal_factor = note.velocity  # Speed of particles along normals
            particleSettings.effector_weights.gravity = 0.1  # Reduce gravity influence to 20%

            # Set the particle system to render the sparkle object
            Brigthness = 4 + (note.velocity * 10)
            particleSettings.render_type = 'OBJECT'
            sparkleName = f"noteSparkles-{trackIndex}-{note.noteNumber}"
            sparkleObj = bDat.objects[sparkleName]
            sparkleObj["emissionStrength"] = Brigthness

            particleSettings.instance_object = sparkleObj
            particleSettings.particle_size = 1.0  # Size of particles
            particleSettings.size_random = 0.2    # 20 % of variability

            # sparkleObj.scale = (1,1,1)
            # sparkleObj.keyframe_insert(data_path="scale", frame=frameTimeOn)

            # sparkleObj.scale = (0,0,0)
            # sparkleObj.keyframe_insert(data_path="scale", frame=frameTimeOff)

        wLog(f"Fireworks V2 - animate {noteCount} sparkles cloud for track {trackIndex}")

    return
