
from config.globals import *
from config.config import bCon, bDat, bOps

# Delete collection and all childs recursively
def deleteCollectionRecursive(collection):
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
    collections = item.users_collection
    if len(collections) > 0:
        return collections[0]
    return context.scene.collection

# Move object to collection
def moveToCollection(collection, obj):
    # First move object to new collection
    collect_to_unlink = findCollection(bCon, obj)
    collection.objects.link(obj)
    collect_to_unlink.objects.unlink(obj)
    
    # Then set parent if _MasterLocation exists
    master_loc_name = f"{collection.name}_MasterLocation"
    if glb.masterLocCollection and master_loc_name in glb.masterLocCollection.objects:
        obj.parent = glb.masterLocCollection.objects[master_loc_name]

# Create collection and master location (empty axis)
def createCollection(colName, colParent, emptyLocMaster = True):
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
    
