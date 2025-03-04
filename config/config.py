"""
Global configuration settings for M2B (MIDI to Blender)

This module contains all global variables and settings used across the application.
It centralizes configuration to make it easier to modify project-wide settings.
"""

import bpy
from config.globals import *

# Global blender objects
bDat = bpy.data
bCon = bpy.context
bScn = bCon.scene
bOps = bpy.ops
bTyp = bpy.types

from enum import Enum

class BlenderObjectType(Enum):
    PLANE = "plane"
    ICOSPHERE = "icosphere"
    UVSPHERE = "uvsphere"
    CUBE = "cube"
    CYLINDER = "cylinder"
    BEZIER_CIRCLE = "bezier_circle"
    LIGHTSHOW = "lightshow"
    POINT = "point"
    EMPTY = "empty"

# MIDI file paths and settings
MIDI_CONFIG = {
    "path": "W:\\MIDI\\FreeMIDI",
    "files": [
        "Air-from Suite No-3 in D",
        "Albinoni",
        "Beethoven-Symphony-5-1",
        "Chopin_Nocturne_op9_n2",
        "Clair de lune",
        "eine-kleine-nachtmusik-mvt1",
        "Fur Elise",
        "Greensleeves",
        "Moonlight-Sonata",
    ],
    "current": "Clair de lune"
}

from sys import platform
    
def getFilesPaths():
    # Get all relevant file paths for current MIDI file
    filename = MIDI_CONFIG["current"]
    base_path = MIDI_CONFIG["path"]
   
    return {
        "midi": f"{base_path}\\{filename}.mid",
        "audio": f"{base_path}\\{filename}.mp3",
        "log": f"{base_path}\\{filename}.log"
    }
