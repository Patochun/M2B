from config.globals import *
from config.config import bDat, bScn, BlenderObjectType
from utils.collection import createCollection
from utils.object import createBlenderObject, createDuplicateLinkedObject
from utils.stuff import wLog, parseRangeFromTracks, extractOctaveAndNote, colorFromNoteNumber
from utils.animation import noteAnimate, distributeObjectsWithClampTo, animCircleCurve
from math import radians, cos, sin, tan, degrees

"""
Creates a fountain-style MIDI visualization with particle trajectories.

This function creates a circular fountain display where:
- Notes are arranged in concentric rings by octave
- Emitters move along circular path
- Particles shoot from emitters to note targets
- Physics-based particle trajectories

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply ("fountain")

Structure:
    - Fountain (main collection)
        - FountainTargets (note target planes)
        - FountainEmitters (moving particle emitters)
            - Trajectory curve
            - Track-based emitters
            - Particle systems

Physics Setup:
    - Particle trajectories calculated with gravity
    - Collision detection on targets
    - Linear emitter movement on curve
    - Particle lifetime based on travel time

Returns:
    None
"""
def createFountain(trackMask, typeAnim):

    wLog(f"Create a Fountain Notes Animation type = {typeAnim}")

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tracksProcessed, tracksColor = parseRangeFromTracks(trackMask)
    tracks = glb.tracks
    fps = glb.fps

    # Create Collection
    fountainCollection = createCollection("Fountain", glb.masterCollection)

    # Create model objects
    fountainModelPlane = createBlenderObject(
        BlenderObjectType.PLANE,
        collection=glb.hiddenCollection,
        name="fountainModelPlane",
        material=glb.matGlobalCustom,
        location=(0, 0, -10),
        height=1,
        width=1
    )

    fountainModelParticle = createBlenderObject(
        BlenderObjectType.CUBE,
        collection=glb.hiddenCollection,
        name="fountainModelParticle",
        material=glb.matGlobalCustom,
        location=(2,0,-10),
        scale=(1,1,1),
        bevel=False
    )

    fountainModelEmitter = createBlenderObject(
        BlenderObjectType.CYLINDER,
        collection=glb.hiddenCollection,
        name="fountainModelEmitter",
        material=glb.matGlobalCustom,
        location=(4,0,-10),
        radius=1,
        height=1
    )

    # Create Target Collection
    fountainTargetCollection = createCollection("FountainTargets", fountainCollection)

    # Construction of the fountain Targets
    theta = radians(360)  # 2 Pi, just one circle
    alpha = theta / 12  # 12 is the Number of notes per octave
    for note in range(132):
        octave, numNote = extractOctaveAndNote(note)
        targetName = f"Target-{numNote}-{octave}"
        targetObj = createDuplicateLinkedObject(fountainTargetCollection, fountainModelPlane, targetName, independant=False)
        spaceY = 0.1
        spaceX = 0.1
        angle = (12 - note) * alpha
        distance = (octave * (1 + spaceX)) + 4
        pX = (distance * cos(angle))
        pY = (distance * sin(angle))
        rot = radians(degrees(angle))
        targetObj.location = (pX, pY, 0)
        targetObj.rotation_euler = (0, 0, rot)
        sX = 1 # mean size of note in direction from center to border (octave)
        sY = (2 * distance * tan(radians(15))) - spaceY # mean size of note in rotate direction (numNote)
        targetObj.scale = (sX, sY, 1)
        targetObj["baseColor"] = colorFromNoteNumber(numNote)
        # Add Taper modifier
        simpleDeformModifier = targetObj.modifiers.new(name="SimpleDeform", type='SIMPLE_DEFORM')
        simpleDeformModifier.deform_method = 'TAPER'
        bigSide = (2 * (distance+sX/2) * tan(radians(15))) - spaceY
        taperFactor = 2*(bigSide/sY-1)
        simpleDeformModifier.factor = taperFactor
                
        # Add collision Physics
        targetObj.modifiers.new(name="Collision", type='COLLISION')  

    wLog("Fountain - create 132 targets")

    # Create Target Collection
    fountainEmitterCollection = createCollection("FountainEmitters", fountainCollection)

    g = -bScn.gravity[2]  # z gravity from blender (m/s^2)

    delayImpact = 3.0  # Time in second from emitter to target
    frameDelayImpact = delayImpact * fps

    # Create empty object for storing somes constants for drivers
    fountainConstantsObj = bDat.objects.new("fountainConstantsValues", None)
    fountainConstantsObj.location=(6,0,-10)
    glb.hiddenCollection.objects.link(fountainConstantsObj)
    fountainConstantsObj["delay"] = delayImpact

    emittersList = []
    for trackCount, trackIndex in enumerate(listOfSelectedTrack):
        track = tracks[trackIndex]

        # Particle
        particleName = f"Particle-{trackIndex}-{track.name}"
        particleObj = createDuplicateLinkedObject(glb.hiddenCollection, fountainModelParticle, particleName,independant=False)
        particleObj.name = particleName
        particleObj.location = (trackIndex * 2, 0, -12)
        particleObj.scale = (0.3,0.3,0.3)
        particleObj["baseColor"] = tracksColor[trackCount]
        particleObj["emissionColor"] = tracksColor[trackCount]
        particleObj["emissionStrength"] = 8.0

        # Emitter around the targets
        emitterName = f"Emitter-{trackIndex}-{track.name}"
        emitterObj = createDuplicateLinkedObject(fountainEmitterCollection, fountainModelEmitter, emitterName,independant=False)
        emittersList.append(emitterObj)

        emitterObj.location = (0, 0, 0)
        emitterObj.scale = (1, 1, 0.2)
        emitterObj["baseColor"] = tracksColor[trackCount]
        emitterObj["emissionColor"] = tracksColor[trackCount]

        # One particle per note
        for noteIndex, note in enumerate(track.notes):

            frameTimeOn = int(note.timeOn * fps)
            frameTimeOff = int(note.timeOff * fps)
            octave, numNote = extractOctaveAndNote(note.noteNumber)

            # Add a particle system to the object
            pSystemName = f"ParticleSystem-{octave}-{noteIndex}"
            particleSystem = emitterObj.modifiers.new(name=pSystemName, type='PARTICLE_SYSTEM')
            pSettingName = f"ParticleSettings-{octave}-{noteIndex}"
            particleSettings = bDat.particles.new(name=pSettingName)
            particleSystem.particle_system.settings = particleSettings

            # Configure particle system settings - Emission
            particleSettings.count = 1
            particleSettings.lifetime = fps * 4
            # Be sure to initialize frame_end before frame_start because
            # frame_start can't be greather than frame_end at any time
            # particleSettings.frame_end = frameTimeOff - frameDelayImpact
            particleSettings.frame_end = frameTimeOn - frameDelayImpact + 1
            particleSettings.frame_start = frameTimeOn - frameDelayImpact

            # Configure particle system settings - Emission - Source
            particleSettings.emit_from = 'FACE'
            particleSettings.distribution = 'GRID'
            particleSettings.grid_resolution = 1
            particleSettings.grid_random = 0

            # Configure particle system settings - Velocity - Using drivers
            # Retrieve Target Object
            targetName = f"Target-{numNote}-{octave}"
            target = bDat.objects[targetName]

            # Add drivers for object_align_factors
            for i, axis in enumerate(['X', 'Y', 'Z']):
                driver = particleSettings.driver_add('object_align_factor', i).driver
                driver.type = 'SCRIPTED'
                
                # Add variables for emitter position
                varE = driver.variables.new()
                varE.name = f"e{axis}"
                varE.type = 'TRANSFORMS'
                varE.targets[0].id = emitterObj
                varE.targets[0].transform_type = f'LOC_{axis}'
                varE.targets[0].transform_space = 'WORLD_SPACE'
                
                # Add variables for target position
                varT = driver.variables.new()
                varT.name = f"t{axis}"
                varT.type = 'TRANSFORMS'
                varT.targets[0].id = target
                varT.targets[0].transform_type = f'LOC_{axis}'
                varT.targets[0].transform_space = 'WORLD_SPACE'
                
                # Add delay variable (from emitter object)
                varDelay = driver.variables.new()
                varDelay.name = "delay" 
                varDelay.type = 'SINGLE_PROP'
                varDelay.targets[0].id = fountainConstantsObj
                varDelay.targets[0].data_path = '["delay"]'

                if axis == 'Z':
                    # driver.expression = f"(t{axis} - e{axis} - 0.5 * g * delay**2) / delay" # initiale expression
                    driver.expression = f"(t{axis} - e{axis} + 4.905 * delay*delay) / delay" # Optimized expression to avoid "Slow Python Expression"
                else:
                    driver.expression = f"(t{axis} - e{axis}) / delay"

            # Configure particle system settings - Render
            particleSettings.render_type = 'OBJECT'
            particleSettings.instance_object = particleObj
            # particleSettings.particle_size = 0.7  # Base size of the particle
            particleSettings.particle_size = note.velocity * 1.4  # Base size of the particle

            # Configure particle system settings - Fields Weights
            particleSettings.effector_weights.gravity = 1

        wLog(f"Fountain - create {noteIndex} particles for track {trackIndex}")

        # Animate target
        for noteIndex, note in enumerate(track.notes):
            octave, numNote = extractOctaveAndNote(note.noteNumber)
            targetName = f"Target-{numNote}-{octave}"
            noteObj = bDat.objects[targetName]
            noteAnimate(noteObj, "MultiLight", track, noteIndex, tracksColor[trackCount])

        wLog(f"Fountain - animate targets with {noteIndex} notes")


    # Create circle curve for trajectory of emitters
    radiusCurve = 20
    fountainEmitterTrajectory = createBlenderObject(
        BlenderObjectType.BEZIER_CIRCLE,
        collection=fountainEmitterCollection,
        name="fountainEmitterTrajectory",
        location=(0, 0, 3),
        radius=radiusCurve
    )

    # emitters along the curve
    distributeObjectsWithClampTo(emittersList, fountainEmitterTrajectory)
    animCircleCurve(fountainEmitterTrajectory, 0.05)

    return
