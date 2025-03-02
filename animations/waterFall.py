from config.globals import *
from config.config import bDat, bScn
from animations.stripNotes import createStripNotes
from utils.stuff import wLog, parseRangeFromTracks
from math import tan

"""
Creates a waterfall visualization of MIDI notes with animated camera movement.

This function creates a waterfall view where:
- Uses strip notes visualization as base
- Adds orthographic camera that follows notes
- Smooth vertical scrolling through timeline
- Notes appear as they are played

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply

Structure:
    - StripNotes (base visualization)
    - Camera
        - Orthographic setup
        - Linear vertical movement
        - Follows note timing

Returns:
    None
"""
def createWaterFall(trackMask, typeAnim):
    
    wLog("Create a waterfall Notes Animation type")

    createStripNotes(trackMask, typeAnim)

    listOfSelectedTrack, noteMin, noteMax, octaveCount, tracksProcessed, tracksColor = parseRangeFromTracks(trackMask)
    tracks = glb.tracks
    fps = glb.fps

    # Initialize a list to store all notes from the selected tracks along with their track index
    selectedNotes = []

    # Iterate through all tracks and collect notes from the selected tracks
    for trackIndex, track in enumerate(tracks):
        if trackIndex in listOfSelectedTrack:  # Check if the current track is selected
            # Add each note as a tuple (trackIndex, note) to the list
            selectedNotes.extend((trackIndex, note) for note in track.notes)

    # Find the tuple with the note that has the smallest timeOn value
    noteMinTimeOn = min(selectedNotes, key=lambda x: x[1].timeOn)
    # Find the tuple with the note that has the largest timeOff value
    noteMaxTimeOff = max(selectedNotes, key=lambda x: x[1].timeOff)

    # Get first and last note object
    noteIndex = tracks[noteMinTimeOn[0]].notes.index(noteMinTimeOn[1])
    FirstNotePlayed = f"Note-{noteMinTimeOn[0]}-{noteMinTimeOn[1].noteNumber}-{noteIndex}"
    noteIndex = tracks[noteMaxTimeOff[0]].notes.index(noteMaxTimeOff[1])
    LastNotePlayed = f"Note-{noteMaxTimeOff[0]}-{noteMinTimeOn[1].noteNumber}-{noteIndex}"
    firstNote = bDat.objects[FirstNotePlayed]
    lastNote = bDat.objects[LastNotePlayed]

    # Create a new camera
    cameraData = bDat.cameras.new(name="Camera")
    cameraObj = bDat.objects.new("Camera", cameraData)
    glb.masterCollection.objects.link(cameraObj)

    # orthographic mode
    cameraData.type = 'ORTHO'

    # Get the sizeX of the background plane
    # Sum sizeX of all object in collection StripNotes/BG
    sizeX = 0
    collectStripeBG = bDat.collections["StripNotes"].children["BG"]
    for obj in collectStripeBG.objects:
        sizeX += obj.scale.x
        
    # objStripePlan = bDat.objects["NotesStripPlane"]
    # sizeX = objStripePlan.scale.x

    # othographic scale (Field of View)
    cameraData.ortho_scale = sizeX # 90

    offSetYCamera = sizeX*(9/16)/2
    orthoFOV = 38.6

    CameraLocationZ = (sizeX/2) / (tan(orthoFOV/2))
    
    # Set the initial position of the camera
    cameraObj.location = (0, offSetYCamera, CameraLocationZ)  # X, Y, Z
    cameraObj.rotation_euler = (0, 0, 0)  # Orientation
    cameraObj.data.shift_y = -0.01

    # Add a keyframe for the starting Y position
    cameraObj.location.y = offSetYCamera + firstNote.location.y - (firstNote.scale.y/2)
    cameraObj.keyframe_insert(data_path="location", index=1, frame=noteMinTimeOn[1].timeOn*fps)

    # Add a keyframe for the starting Y position
    cameraObj.location.y = offSetYCamera + lastNote.location.y + (lastNote.scale.y/2)
    cameraObj.keyframe_insert(data_path="location", index=1, frame=noteMaxTimeOff[1].timeOff*fps)

    # Set the active camera for the scene
    bScn.camera = cameraObj

    # Make animation linear
    action = cameraObj.animation_data.action  # Get animation action
    fcurve = action.fcurves.find(data_path="location", index=1)  # F-Curve for Y axis

    if fcurve:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = 'LINEAR'  # Set interpolation to 'LINEAR'
