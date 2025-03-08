"""

M2B - MIDI To Blender

Generate 3D objects animated from midifile

Author   : Patochun (Patrick M)
Mail     : ptkmgr@gmail.com
YT       : https://www.youtube.com/channel/UCCNXecgdUbUChEyvW3gFWvw
Create   : 2024-11-11
Version  : 10.0
Compatibility : Blender 4.0 and above

Licence used : GNU GPL v3
Check licence here : https://www.gnu.org/licenses/gpl-3.0.html

Comments : M2B, a script to generate 3D objects animated from midifile

Usage : All parameters like midifile used and animation choices are hardcoded in the script

"""

# Import necessary modules
# modules standard
import time  # Provides time-related functions
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from math import ceil

# reload project modules
# from utils.modules import reloadProjectModules  # Import the function (adjust path if needed)
# reloadProjectModules()  # Reload all project modules automatically

# modules M2B
from config.globals import *
from config.config import getFilesPaths, bScn
from utils.stuff import initLog, wLog, endLog, createCompositorNodes, determineGlobalRanges, loadaudio
from utils.midi import readMIDIFile
from utils.collection import initCollections, toggleCollectionCollapse
from utils.object import initMaterials
from animations.animate import animate  

###############################################################################
#                                    MAIN                                     #
###############################################################################
"""
Primary execution point for MIDI to Blender animation generation.

Configuration:
    path: Base path for MIDI/audio files
    filename: Name of MIDI file to process
    typeAnim: Animation style to generate

Output:
    - 3D visualization in Blender
    - Log file with execution details
    - Optional audio synchronization

Usage:
    Set desired animation type by uncommenting appropriate createX() call
"""
timeStart = time.time()

# initGlobals()
paths = getFilesPaths()
initLog(paths["log"])
initCollections()
initMaterials()

# get blender fps
glb.fps = bScn.render.fps

# Import midi Datas
midiFile, TempoMap, glb.tracks = readMIDIFile(paths["midi"])

wLog(f"Midi file path = {paths['midi']}")
wLog(f"Midi type = {midiFile.midiFormat}")
wLog(f"PPQN = {midiFile.ppqn}")
wLog(f"Number of tracks = {len(glb.tracks)}")

loadaudio(paths["audio"])

noteMinAllTracks, noteMaxAllTracks, firstNoteTimeOn, glb.lastNoteTimeOff, noteMidRangeAllTracks = determineGlobalRanges()

# animate("barGraph", "0-15", "ZScale,B2R-Light")
# animate("stripNotes", "0-15", "B2R-Light")
# animate("waterFall", "0-30", "B2R-Light")
# animate("fireworksV1", "0-15", "Spread")
# animate("fireworksV2", "0-15", "Spread")
# animate("fountain", "0-15", "fountain")
animate("lightShow", "0-15", "Cycle")

bScn.frame_end = ceil(glb.lastNoteTimeOff + 5) * glb.fps
createCompositorNodes() 
toggleCollectionCollapse(2)

# Close log file
wLog(f"Script Finished: {time.time() - timeStart:.2f} sec")
endLog()
