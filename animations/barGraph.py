from config.globals import *
from config.config import bDat, BlenderObjectType
from utils.collection import createCollection
from utils.object import createBlenderObject, createDuplicateLinkedObject
from utils.animation import noteAnimate
from utils.stuff import wLog, parseRangeFromTracks, colorFromNoteNumber

"""
Creates a bar graph visualization for MIDI tracks in Blender.

This function creates a 3D bar graph visualization where:
- Each track gets a row of cubes
- Each cube represents a note
- X axis: Note positions (octaves)
- Y axis: Track positions 
- Z axis: Note velocity animation
- Background planes show octave ranges

Parameters:
    masterCollection (bpy.types.Collection): Parent collection for organization
    trackMask (str): Track selection pattern (e.g. "0-5,7,9-12")
    typeAnim (str): Animation style to apply ("ZScale", "B2R-Light", etc)
"""

def createBlenderBGAnimation(trackMask, typeAnim):
    wLog(f"Create a BarGraph Animation type = {typeAnim}")
    
    listOfSelectedTrack, noteMin, noteMax, octaveCount, numberOfRenderedTracks, tracksColor = parseRangeFromTracks(trackMask)
    tracks = glb.tracks

    # Create master BG collection
    BGCollect = createCollection("BarGraph", glb.masterCollection)

    # Create models Object
    BGModelCube = createBlenderObject(
        BlenderObjectType.CUBE,
        collection=glb.hiddenCollection,
        name="BGModelCube",
        material=glb.matGlobalCustom,
        location=(0,0,-5),
        scale=(1,1,1),
        bevel=False
    )

    BGModelPlane = createBlenderObject(
        BlenderObjectType.PLANE,
        collection=glb.hiddenCollection,
        name="BGModelPlane",
        material=glb.matGlobalCustom,
        location=(0,0,-5),
        height=1,
        width=1
    )
        
    # Create cubes from track
    # Parse track to create BG
    trackCenter = numberOfRenderedTracks / 2
    noteMidRange = (noteMin + noteMax) / 2
    cubeSpace = BGModelCube.scale.x * 1.2 # mean x size of cube + 20 %

    # Parse track to create BG
    for trackCount, trackIndex in enumerate(listOfSelectedTrack):
        track = tracks[trackIndex]

        # create collection
        BGTrackName = f"BG-{trackIndex}-{track.name}"
        BGTrackCollect = createCollection(BGTrackName, BGCollect)

        # one cube per note used
        for note in track.notesUsed:
            # create cube
            cubeName = f"Cube-{trackIndex}-{note}"
            offsetX = (note - noteMidRange) * cubeSpace
            offsetY = (trackCount - trackCenter) * cubeSpace + cubeSpace / 2
            cubeLinked = createDuplicateLinkedObject(BGTrackCollect, BGModelCube, cubeName, independant=False)
            cubeLinked.location = (offsetX, offsetY, 0)
            cubeLinked["baseColor"] = colorFromNoteNumber(note % 12)
                
        wLog(f"BarGraph - create {len(track.notesUsed)} cubes for track {trackIndex} (range noteMin-noteMax) ({track.minNote}-{track.maxNote})")

    # Create a plane by octave to have a visualisation for them
    # minnote and maxnote are usefull to know the range of octave
    minOctave = noteMin // 12
    maxOctave = noteMax // 12
    
    BGPlaneCollect = createCollection("BG-Plane", BGCollect)

    planPosXOffset = (((noteMidRange % 12) - 5) * cubeSpace) - (cubeSpace / 2)
    for octave in range(minOctave, maxOctave + 1):
        planSizeX = 12 * cubeSpace
        planSizeY = (trackCount + 1) * cubeSpace
        planPosX = (octave - (noteMidRange // 12)) * 12 * cubeSpace
        planPosX -= planPosXOffset
        planeName = f"Plane-{octave}"
        obj = createDuplicateLinkedObject(BGPlaneCollect, BGModelPlane, planeName, independant=False)
        obj.scale = (planSizeX, planSizeY, 1)
        obj.location = (planPosX, 0, (-BGModelCube.scale.z / 2)*1.005)
        if octave % 2 == 0:
            obj["baseColor"] = 0.6 # Yellow
        else: 
            obj["baseColor"] = 1.0 # Cyan

    # Animate cubes accordingly to notes event
    for trackCount, trackIndex in enumerate(listOfSelectedTrack):
        # wLog(f"trackCount={trackCount} & trackIndex={trackIndex}")
        track = tracks[trackIndex]
        for noteIndex, note in enumerate(track.notes):
            # Construct the cube name and animate
            cubeName = f"Cube-{trackIndex}-{note.noteNumber}"
            noteObj = bDat.objects[cubeName]
            noteAnimate(noteObj, typeAnim, track, noteIndex, tracksColor[trackCount])

        wLog(f"BarGraph - Animate cubes for track {trackIndex} (notesCount) ({noteIndex})")
        
    return

    
    