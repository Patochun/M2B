from config.globals import *
from config.config import BlenderObjectType
from utils.collection import createCollection
from utils.object import createBlenderObject, createDuplicateLinkedObject
from utils.animation import noteAnimate
from utils.stuff import wLog, parseRangeFromTracks, colorFromNoteNumber, extractOctaveAndNote
from math import ceil

"""
Creates a strip-based visualization of MIDI notes with animations.

This function creates a vertical strip visualization where:
- Each note is represented by a rectangle
- X axis: Note pitch and track offset
- Y axis: Time (note start/duration)
- Background plane shows total time range
- Notes are colored by track

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply ("ZScale", "B2R-Light", etc)

Structure:
    - StripNotes (main collection)
        - Notes-TrackN (per track collections)
            - Note rectangles
        - NotesStripPlane (background)

Returns:
    bpy.types.Object: The created background plane object

"""
def createStripNotes(trackMask, typeAnim):

    wLog(f"Create a Strip Notes Animation type = {typeAnim}")

    listOfSelectedTrack, noteMin, noteMax, octaveCount, trackProcessed, tracksColor = parseRangeFromTracks(trackMask)
    tracks = glb.tracks
    
    # Create models Object
    stripModelCube = createBlenderObject(
        BlenderObjectType.CUBE,
        collection=glb.hiddenCollection,
        name="StripNotesModelCube",
        material=glb.matGlobalCustom,
        location=(0,0,-5),
        scale=(1,1,1),
        bevel=False
    )

    stripModelPlane = createBlenderObject(
        BlenderObjectType.PLANE,
        collection=glb.hiddenCollection,
        name="StripBGModelPlane",
        material=glb.matGlobalCustom,
        location=(0, 0, -10),
        width=1,
        height=1
    )

    stripCollect = createCollection("StripNotes", glb.masterCollection)

    notecount = (noteMax - noteMin) + 1
    noteMiddle = noteMin + ceil(notecount / 2)

    marginExtX = 0 # in ?
    marginExtY = 0 # in sec
    cellSizeX = 1 # size X for each note in centimeters
    cellSizeY = 4 # size for each second in centimeters
    intervalX = cellSizeX / 10
    intervalTracks = (cellSizeX + intervalX) * (trackProcessed)

    # Parse tracks
    length = 0
    for trackCount, trackIndex in enumerate(listOfSelectedTrack):
        track = tracks[trackIndex]

        length = max(length, track.notes[-1].timeOff)
        offSetX = ((trackCount) * (cellSizeX + intervalX))
        intervalY = 0 # have something else to 0 create artefact in Y depending on how many note
        
        # Create collections
        notesCollection = createCollection(f"Notes-Track-{trackCount}", stripCollect)

        sizeX = cellSizeX

        for noteIndex, note in enumerate(track.notes):
            posX = ((note.noteNumber - noteMiddle) * (intervalTracks)) + offSetX # - (sizeX / 2)
            sizeY = round(((note.timeOff - note.timeOn) * cellSizeY),2)
            posY = ((marginExtY + note.timeOn) * (cellSizeY + intervalY)) + (sizeY / 2)
            nameOfNotePlayed = f"Note-{trackCount}-{note.noteNumber}-{noteIndex}"

            # Duplicate the existing note
            noteObj = createDuplicateLinkedObject(notesCollection, stripModelCube, nameOfNotePlayed, independant=False)
            noteObj.location = (posX, posY, 0) # Set instance position
            noteObj.scale = (sizeX, sizeY, 1) # Set instance scale
            noteObj["baseColor"] = tracksColor[trackCount]

            # Animate note
            # Be aware to animate duplicate only, never the model one
            # Pass the current note, previous note, and next note to the function
            noteAnimate(noteObj, typeAnim, track, noteIndex, tracksColor[trackCount])
            
        wLog(f"Notes Strip track {trackCount} - create & animate {noteIndex + 1}")

    # Create background plane
    planSizeX = (marginExtX * 2) + (notecount * cellSizeX) + (notecount * intervalTracks)
    planSizeY = (length + (marginExtY *2)) * cellSizeY

    BGCollection = createCollection(f"BG", stripCollect)

    for noteNum in range(noteMin, noteMax + 1):
        planeName = (f"{noteNum}-BG")
        planeObj = createDuplicateLinkedObject(BGCollection, stripModelPlane, planeName, independant=False)
        planeObj.scale = (intervalTracks, planSizeY, 1)
        planeObj.location = (((noteNum - noteMiddle) * intervalTracks) + intervalTracks / 2 - cellSizeX / 2, planSizeY / 2, (-stripModelCube.scale.z / 2))
        octave, note = extractOctaveAndNote(noteNum)
        color = 0.400 + colorFromNoteNumber(noteNum % 12) * 4
        if octave % 2 == 0:
            color += 0.1
        planeObj["baseColor"] = color
        planeObj["baseSaturation"] = 0.4

    return
