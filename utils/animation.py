
from config.globals import *
from config.config import bTyp
from utils.stuff import wLog
from math import ceil, sin, pi
from random import randint

"""
Animate a Blender object based on MIDI note events and animation type.

This function handles different animation styles for visualizing MIDI notes:
- ZScale: Vertical scaling based on note velocity
- Light: Emission strength and color based on velocity
- MultiLight: Multi-colored emission based on track color
- Spread: Particle cloud expansion effect

Parameters:
    Obj (bpy.types.Object): Blender object to animate
    typeAnim (str): Animation style(s), comma-separated
    note (MIDINote): Current note to process
    previousNote (MIDINote): Previous note in sequence
    nextNote (MIDINote): Next note in sequence
    colorTrack (float): Color value for track (0.0-1.0)

Animation Timing:
    - frameT1: Note start
    - frameT2: Start transition complete
    - frameT3: End transition start
    - frameT4: Note end

Properties Animated:
    - location: (x,y,z) position
    - scale: (x,y,z) size
    - emissionColor: Material emission color
    - emissionStrength: Material emission intensity
    - modifiers: Geometry nodes parameters

Returns:
    None
"""
def noteAnimate(obj, typeAnim, track, noteIndex, colorTrack):

    fps = glb.fps
    note = track.notes[noteIndex]

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

    eventLenMove = max(1, min(ceil(fps * 0.1), (note.timeOff - note.timeOn) * fps // 2))

    frameTimeOn = int(note.timeOn * fps)
    frameTimeOff = max(frameTimeOn + 2, int(note.timeOff * fps))

    frameT1, frameT2 = frameTimeOn, frameTimeOn + eventLenMove
    frameT3, frameT4 = frameTimeOff - eventLenMove, frameTimeOff

    frameTimeOffPrevious = int(previousNote.timeOff * fps) if previousNote else frameTimeOn
    frameTimeOnNext = int(nextNote.timeOn * fps) if nextNote else frameTimeOff
    
    if frameTimeOn < frameTimeOffPrevious or frameTimeOff > frameTimeOnNext:
        return
    
    # Transform linear velocity (0-1) into sinusoidal brightness curve
    brightness = 5 + (sin(note.velocity * pi/2) * 2)

    # List of keyframes to animate
    keyframes = []

    # Handle different animation types
    for animation_type in typeAnim.split(','):
        match animation_type.strip():
            case "ZScale":
                velocity = 3 * note.velocity
                keyframes.extend([
                    (frameT1, "scale", (None, None, 1)),
                    (frameT1, "location", (None, None, 0)),
                    (frameT2, "scale", (None, None, velocity)),
                    (frameT2, "location", (None, None, (velocity - 1) / 2)),
                    (frameT3, "scale", (None, None, velocity)),
                    (frameT3, "location", (None, None, (velocity - 1) / 2)),
                    (frameT4, "scale", (None, None, 1)),
                    (frameT4, "location", (None, None, 0)),
                ])
            
            case "B2R-Light":
                adjustedVelocity = 2 * (note.velocity ** 2) if note.velocity < 0.5 else 1 - 2 * ((1 - note.velocity) ** 2)
                velocityBlueToRed = 0.02 + (0.4 - 0.02) * adjustedVelocity
                keyframes.extend([
                    (frameT1, "emissionColor", velocityBlueToRed),
                    (frameT1, "emissionStrength", 0.0),
                    (frameT2, "emissionColor", velocityBlueToRed),
                    (frameT2, "emissionStrength", brightness),
                    (frameT3, "emissionColor", velocityBlueToRed),
                    (frameT3, "emissionStrength", brightness),
                    (frameT4, "emissionColor", velocityBlueToRed),
                    (frameT4, "emissionStrength", 0.0),
                ])
            
            case "MultiLight":
                # If the object has an emission color from another track, average it
                if obj["emissionColor"] > 0.01:
                    colorTrack = (obj["emissionColor"] + colorTrack) / 2
                keyframes.extend([
                    (frameT1, "emissionColor", colorTrack),
                    (frameT2, "emissionColor", colorTrack),
                    (frameT3, "emissionColor", colorTrack),
                    (frameT4, "emissionColor", colorTrack),
                    (frameT4, "emissionColor", obj["baseColor"]),
                    (frameT1, "emissionStrength", 0.0),
                    (frameT2, "emissionStrength", brightness),
                    (frameT3, "emissionStrength", brightness),
                    (frameT4, "emissionStrength", 0.0),
                ])
            
            case "Spread":
                posZ = note.velocity * 30
                radius = min((frameT4 - frameT1) // 2, 5)
                densityCloud = obj.modifiers["SparklesCloud"].node_group.interface.items_tree["densityCloud"].identifier
                densitySeed = obj.modifiers["SparklesCloud"].node_group.interface.items_tree["densitySeed"].identifier
                
                keyframes.extend([
                    (frameT1, "location", (None, None, posZ)),
                    (frameT1, "scale", (0, 0, 0)),
                    (frameT1, "emissionStrength", 0),
                    (frameT1, f'modifiers.SparklesCloud.{densityCloud}', note.velocity / 3),
                    (frameT1, f'modifiers.SparklesCloud.{densitySeed}', randint(0, 1000)),
                    (frameT2, "scale", (radius, radius, radius)),
                    (frameT2, "emissionStrength", 20),
                    (frameT4, "scale", (0, 0, 0)),
                    (frameT4, "emissionStrength", 0),
                    (frameT4, f'modifiers.SparklesCloud.{densitySeed}', randint(0, 1000)),
                ])
            
            case _:
                wLog(f"Unknown animation type: {animation_type}")
    
    # noteStatus animation
    keyframes.extend([
        (frameT1, "noteStatus", 0.0),
        (frameT2, "noteStatus", note.velocity),
        (frameT3, "noteStatus", note.velocity),
        (frameT4, "noteStatus", 0.0),
    ])

    keyframes.sort(key=lambda x: (x[0], x[1]))
    
    for frame, data_path, value in keyframes:
        if isinstance(value, tuple):
            # Handle vector properties (location, scale)
            for i, v in enumerate(value):
                if v is not None:
                    val = getattr(obj, data_path) # Get vector value
                    val[i] = v  # set value with index i (0=x, 1=y, 2=z)
                    setattr(obj, data_path, val)  # Apply change
                    obj.keyframe_insert(data_path=f"{data_path}", index=i, frame=frame)
        else:
            # Handle custom properties with proper data path
            if data_path in ["noteStatus","emissionColor", "emissionStrength"]:
                obj[data_path] = value
                obj.keyframe_insert(data_path=f'["{data_path}"]', frame=frame)
            elif data_path.startswith('modifiers'):
                # Handle modifier properties
                modDataPath = data_path.split('.')[1]
                modDataIndex = data_path.split('.')[2]
                obj.modifiers[modDataPath][modDataIndex] = value
                data_path = f'modifiers["{modDataPath}"]["{modDataIndex}"]'
                obj.keyframe_insert(data_path=data_path, frame=frame)
            else:
                # Handle regular properties
                obj[data_path] = value
                obj.keyframe_insert(data_path=data_path, frame=frame)


"""
Distributes objects evenly along a Bezier curve using Clamp To constraints.

Args:
    listObj (list): List of objects to distribute along the curve
    curve (bpy.types.Object): Target Bezier curve object
    
The function:
- Calculates even spacing between objects
- Adds Clamp To constraint to each object
- Sets initial positions proportionally along curve
- Maintains dynamic curve following with influence=1

Note:
    Objects will be clamped to curve while maintaining even distribution
    Positioning uses curve dimensions for initial placement
    Constraint influence is set to 1 to maintain curve following
"""
def distributeObjectsWithClampTo(listObj: list, curve: bTyp.Object):
    numObjects = len(listObj)

    # Adjust factor based on number of objects
    baseFactor = curve.dimensions.x + 2
    factor = baseFactor / numObjects

    for i, obj in enumerate(listObj):

        # Compute initial position before applying Clamp To
        obj.location.x = factor * (i+1)

        # Apply the Clamp To modifier
        clampMod = obj.constraints.new(type='CLAMP_TO')
        clampMod.target = curve
        clampMod.use_cyclic = True
        clampMod.main_axis = 'CLAMPTO_X'
        clampMod.influence = 1.0

"""
Animate rotation of a curve based on rotation speed and note duration.

Args:
    curve (bpy.types.Object): Curve object to animate
    rotationSpeed (float): Rotations per second

Note:
    Uses global lastNoteTimeOff and fps variables
    Creates linear animation from start to end
"""
def animCircleCurve(curve, rotationSpeed):
    # Animate circle curve with rotationSpeed = Rotations per second
    startFrame = 1
    endFrame = int(glb.lastNoteTimeOff * glb.fps)  # Use global lastNoteTimeOff
    totalRotations = rotationSpeed * glb.lastNoteTimeOff

    # Set keyframes for Z rotation
    curve.rotation_euler.z = 0
    curve.keyframe_insert(data_path="rotation_euler", index=2, frame=startFrame)

    curve.rotation_euler.z = totalRotations * 2 * pi  # Convert to radians
    curve.keyframe_insert(data_path="rotation_euler", index=2, frame=endFrame)

    # Make animation linear
    for fcurve in curve.animation_data.action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = 'LINEAR'
