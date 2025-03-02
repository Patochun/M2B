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
    "current": "Greensleeves"
}

from utils.stuff import CreateMatGlobalCustom
from sys import platform

"""
Purge all orphaned (unused) data in the current Blender file.
This includes unused objects, materials, textures, collections, particles, etc.
"""
def purgeUnusedDatas():
    purgedItems = 0
    dataCategories = [
        bDat.objects, bDat.curves, bDat.meshes, bDat.materials,
        bDat.textures, bDat.images, bDat.particles, bDat.node_groups,
        bDat.actions, bDat.collections, bDat.sounds
    ]
    
    for dataBlock in dataCategories:
        for item in list(dataBlock):  # Use list() to avoid modifying during iteration
            if not item.users:
                dataBlock.remove(item)
                purgedItems += 1
    
    # wLog(f"Purging complete. {purgedItems} orphaned data cleaned up.")

def initGlobals():
    """Initialize global variables that require Blender context"""
    
    # Create main collections
    glb.masterCollection = bpy.data.collections.new("M2B")
    bScn.collection.children.link(glb.masterCollection)

    purgeUnusedDatas()
    
    glb.masterLocCollection = bpy.data.collections.new("MasterLocation") 
    glb.masterCollection.children.link(glb.masterLocCollection)
    
    glb.hiddenCollection = bpy.data.collections.new("Hidden")
    glb.masterCollection.children.link(glb.hiddenCollection)
    glb.hiddenCollection.hide_viewport = True
    
    # Create global material
    glb.matGlobalCustom = CreateMatGlobalCustom()

    # get blender fps
    glb.fps = bScn.render.fps
    
def getFilesPaths():
    # Get all relevant file paths for current MIDI file
    filename = MIDI_CONFIG["current"]
    base_path = MIDI_CONFIG["path"]
   
    return {
        "midi": f"{base_path}\\{filename}.mid",
        "audio": f"{base_path}\\{filename}.mp3",
        "log": f"{base_path}\\{filename}.log"
    }
 