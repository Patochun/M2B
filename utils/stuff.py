from config.globals import *
from config.config import bDat, bScn, bCon, bOps
from os import path

# Open log file for append
def initLog(logFile):
    glb.fLog = open(logFile, "w+")

# write to screen and log
def wLog(toLog):
    print(toLog)
    glb.fLog.write(toLog+"\n")
    
# Close logFile
def endLog():
    glb.fLog.close()

import re

"""
    Parses a range string and returns a list of numbers.
    Example input: "1-5,7,10-12"
    Example output: [1, 2, 3, 4, 5, 7, 10, 11, 12]
    return some values calculated from effective range, noteMin, noteMax, octaveCount, effectiveTrackCount
"""
def parseRangeFromTracks(rangeStr):

    def max_gap_values(n, start=0.02, end=1):
        """
        Returns a list of n values between start and end,
        arranged so that the gap between consecutive values is maximized.
        The output list is not in ascending order.
        """
        if n < 1:
            raise ValueError("n must be a positive integer")
        if n == 1:
            return [(start + end) / 2]  # Return the mid value if only one element is needed

        # Generate n equally spaced values between start and end
        step = (end - start) / (n - 1)
        sorted_values = [start + i * step for i in range(n)]

        # Reorder the list to maximize differences between consecutive values
        result = []
        # Start with the middle element
        mid_index = len(sorted_values) // 2
        result.append(sorted_values.pop(mid_index))

        # Alternate: take successivement le plus petit et le plus grand élément restant
        toggle = True
        while sorted_values:
            if toggle:
                result.append(sorted_values.pop(0))
            else:
                result.append(sorted_values.pop(-1))
            toggle = not toggle

        return result

    tracks = glb.tracks
    wLog(f"Track filter used = {rangeStr}")

    numbers = []
    if rangeStr == "*":
        numbers = range(len(tracks))
    else:
        # Divide string in individuals parts
        segments = rangeStr.split(',')

        for segment in segments:
            match = re.match(r'^(\d+)-(\d+)$', segment)
            if match:  # Case of range like "1-16"
                start, end = map(int, match.groups())
                numbers.extend(range(start, end + 1))
            elif re.match(r'^\d+$', segment):  # Case of single number
                numbers.append(int(segment))
            else:
                raise ValueError(f"Invalid format : {segment}")

    # Evaluate noteMin, noteMax and octaveCount from effective range
    noteMin = 1000
    noteMax = 0
    effectiveTrackCount = 0
    tracksSelected = ""
    listOfSelectedTracks = []
    for trackIndex, track in enumerate(tracks):
        if trackIndex not in numbers:
            continue
        
        effectiveTrackCount += 1
        tracksSelected += (f"{trackIndex},")
        listOfSelectedTracks.append(trackIndex)
        noteMin = min(noteMin, track.minNote)
        noteMax = max(noteMax, track.maxNote)

    tracksSelected = tracksSelected[:-1]  # Remove last ,
    wLog(f"Track selected are = {tracksSelected}")

    octaveCount = (noteMax // 12) - (noteMin // 12) + 1

    # Create a table of color
    tracksColor = max_gap_values(effectiveTrackCount, start=0.02, end=1)

    return listOfSelectedTracks, noteMin, noteMax, octaveCount, effectiveTrackCount, tracksColor

# Define color from note number when sharp (black) or flat (white)
def colorFromNoteNumber(noteNumber):
    if noteNumber in [1, 3, 6, 8, 10]:
        return 0.001  # Black note (almost)
    else:
        return 0.01 # White note

# Retrieve octave and noteNumber from note number (0-127)
def extractOctaveAndNote(noteNumber):
    octave = noteNumber // 12
    noteNumber = noteNumber % 12
    return octave, noteNumber

"""
Creates a Compositor node setup for post-processing effects

This function sets up a basic compositor node network for adding bloom/glare effects
to the final render. It creates and configures:

Node Setup:
    - Render Layers: Source of rendered image
    - Glare: Adds bloom effect
      - Type: BLOOM
      - Quality: MEDIUM
      - Mix: 0.0
      - Threshold: 5
      - Size: 4
    - Composite: Final output

Parameters:
    None

Returns:
    None

Usage:
    createCompositorNodes()
"""
def createCompositorNodes():

    # Enable the compositor
    bScn.use_nodes = True
    nodeTree = bScn.node_tree

    # Remove existing nodes
    for node in nodeTree.nodes:
        nodeTree.nodes.remove(node)

    # Add necessary nodes
    renderLayersNode = nodeTree.nodes.new(type='CompositorNodeRLayers')
    renderLayersNode.location = (0, 0)

    glareNode = nodeTree.nodes.new(type='CompositorNodeGlare')
    glareNode.location = (300, 0)

    # Configure the Glare node
    glareNode.glare_type = 'BLOOM'
    glareNode.quality = 'MEDIUM'
    glareNode.mix = 0.0
    glareNode.threshold = 5
    glareNode.size = 4

    compositeNode = nodeTree.nodes.new(type='CompositorNodeComposite')
    compositeNode.location = (600, 0)

    # Connect the nodes
    links = nodeTree.links
    links.new(renderLayersNode.outputs['Image'], glareNode.inputs['Image'])
    links.new(glareNode.outputs['Image'], compositeNode.inputs['Image'])
    
    return


# Define blender unit system
def setBlenderUnits(unitScale=0.01, lengthUnit="CENTIMETERS"):
    bScn.unit_settings.system = 'METRIC'
    bScn.unit_settings.system_rotation = 'DEGREES'
    bScn.unit_settings.length_unit = lengthUnit
    bScn.unit_settings.scale_length = unitScale

    for area in bCon.screen.areas:
        if area.type == 'VIEW_3D':  # check if it is a 3D view
            for space in area.spaces:
                if space.type == 'VIEW_3D':  # check 3D space in editor
                    # Modifier l'échelle de la grille
                    space.overlay.grid_scale = 0.01
                    space.clip_end = 10000.0
                    break

# Determine global min/max ranges for scene configuration
def determineGlobalRanges():
    """
    Calculate global note and time ranges across all tracks.
    
    Args:
        tracks: List of MIDI tracks
        
    Returns:
        tuple: (noteMin, noteMax, timeMin, timeMax)
    """
    tracks = glb.tracks
    stats = {
        'noteMin': 1000,
        'noteMax': 0,
        'timeMin': 1000,
        'timeMax': 0,
        'noteMidRange': 0
    }
    
    for track in tracks:
        stats.update({
            'noteMin': min(stats['noteMin'], track.minNote),
            'noteMax': max(stats['noteMax'], track.maxNote),
            'timeMin': min(stats['timeMin'], track.notes[0].timeOn),
            'timeMax': max(stats['timeMax'], track.notes[-1].timeOff)
        })

    # Calculate mid range for centering
    stats['noteMidRange'] = stats['noteMin'] + (stats['noteMax'] - stats['noteMin']) / 2

    wLog(f"Note range: {stats['noteMin']} to {stats['noteMax']} (mid: {stats['noteMidRange']})")
    wLog(f"Time range: {stats['timeMin']:.2f}s to {stats['timeMax']:.2f}s")
    
    return (stats['noteMin'], stats['noteMax'], stats['timeMin'], stats['timeMax'], stats['noteMidRange'])


# load audio file mp3 with the same name of midi file if exist
# into sequencerdef loadaudio(paths):
def loadaudio(paths):
    if path.exists(paths):
        if not bScn.sequence_editor:
            bScn.sequence_editor_create()

        # Clear the VSE, then add an audio file
        bScn.sequence_editor_clear()
        my_contextmem = bCon.area.type
        my_context = 'SEQUENCE_EDITOR'
        bCon.area.type = my_context
        my_context = bCon.area.type
        bOps.sequencer.sound_strip_add(filepath=paths, relative_path=True, frame_start=1, channel=1)
        bCon.area.type = my_contextmem
        my_context = bCon.area.type
        wLog("Audio file mp3 is loaded into VSE")
    else:
        wLog("Audio file mp3 not exist")
