
from config.globals import *
from config.config import bCon, bDat, bOps, bScn
from utils.stuff import wLog

# Delete collection and all childs recursively
def deleteCollectionRecursive(collection):
    """
    Recursively delete a collection and all its child collections and objects.

    Args:
    collection (bpy.types.Collection): The collection to delete.

    Returns:
    None
    """
    # First delete all child collections recursively
    for child in collection.children:
        deleteCollectionRecursive(child)

    # Then delete all objects in this collection
    for obj in collection.objects:
        bDat.objects.remove(obj, do_unlink=True)

    # Finally remove the collection itself
    bDat.collections.remove(collection)


# Research about a collection
def findCollection(context, item):
    """
    This function searches for the collection that contains the given item.

    Parameters:
    context (bpy.types.Context): The current Blender context.
    item (bpy.types.ID): The Blender data-block to search for. This can be an object, a scene, etc.

    Returns:
    bpy.types.Collection: The first collection containing the item, or the active scene's collection if the item is not in any collection.
    """
    collections = item.users_collection
    if len(collections) > 0:
        return collections[0]
    return context.scene.collection


# Move object to collection
def moveToCollection(collection, obj):
    """
    This function moves an object to a new collection.
    If a master location object exists for the new collection, it sets the moved object's parent to this master location object.

    Parameters:
    collection (bpy.types.Collection): The collection to which the object will be moved.
    obj (bpy.types.Object): The Blender object that will be moved to the new collection.

    Returns:
    None
    """
    # First move object to new collection
    collect_to_unlink = findCollection(bCon, obj)
    collection.objects.link(obj)
    collect_to_unlink.objects.unlink(obj)

    # Then set parent if _MasterLocation exists
    master_loc_name = f"{collection.name}_MasterLocation"
    if glb.masterLocCollection and master_loc_name in glb.masterLocCollection.objects:
        obj.parent = glb.masterLocCollection.objects[master_loc_name]


# Create collection and master location (empty axis)
def createCollection(colName, colParent, emptyLocMaster=True):
    """
    This function creates a new collection under a specified parent collection.
    If the collection already exists, it will be deleted first.
    If 'emptyLocMaster' is True, an empty object will be created as the master location for the new collection.

    Parameters:
    colName (str): The name of the new collection.
    colParent (bpy.types.Collection): The parent collection under which the new collection will be created.
    emptyLocMaster (bool, optional): Whether to create an empty master location object for the new collection. Defaults to True.

    Returns:
    bpy.types.Collection: The newly created collection.
    """
    # Delete if exists with all children
    if colName in bDat.collections:
        collection = bDat.collections[colName]
        deleteCollectionRecursive(collection)

    # create a new one
    newCollection = bDat.collections.new(colName)
    colParent.children.link(newCollection)

    if emptyLocMaster:
        # create an empty axis to be parent for all objects in the collection
        bOps.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
        empty = bCon.active_object
        empty.name = f"{colName}_MasterLocation"

        # Check if parent collection has an empty and set parent
        parent_empty_name = f"{colParent.name}_MasterLocation"

        if parent_empty_name in glb.masterLocCollection.objects:
            empty.parent = glb.masterLocCollection.objects[parent_empty_name]

        moveToCollection(glb.masterLocCollection, empty)

    return newCollection


def toggleCollectionCollapse(state):
    area = next(a for a in bCon.screen.areas if a.type == "OUTLINER")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bCon.temp_override(area=area, region=region):
        bOps.outliner.show_hierarchy("INVOKE_DEFAULT")
        for i in range(state):
            # Expand/Collapse all items
            bOps.outliner.expanded_toggle()
    area.tag_redraw()

    # https://projects.blender.org/blender/blender/issues/125522
    
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
    
    wLog(f"Purging complete. {purgedItems} orphaned data cleaned up.")

def initCollections():
    """Initialize global variables that require Blender context"""

    # Create main collections
    # Get default collection using scene's master collection
    colDefault = bCon.scene.collection.children[0]  # First child is always the default collection

    glb.masterCollection = createCollection("M2B", colDefault, False)
    purgeUnusedDatas()
    glb.masterLocCollection = createCollection("MasterLocation", glb.masterCollection, False) 
    glb.hiddenCollection = createCollection("Hidden", glb.masterCollection, False)
    glb.hiddenCollection.hide_viewport = True
