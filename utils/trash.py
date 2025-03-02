from config.config import bScn, bCon, bOps
from utils.stuff import wLog

# Maximize aera view in all windows.
# type = VIEW_3D
# type = OUTLINER
def GUI_maximizeAeraView(type):
    for window in bCon.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == type:
                with bCon.temp_override(window=window, area=area):
                    bOps.screen.screen_full_area()
                break
    
def collapseAllCollectionInOutliner():
    for window in bCon.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == "OUTLINER":
                with bCon.temp_override(window=window, area=area):
                    bOps.outliner.expanded_toggle()
                break

    wLog("No OUTLINER area found in the current context.")

def viewportShadingRendered():
    # Enable viewport shading in Rendered mode
    for area in bCon.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'RENDERED'

    # Enable compositor (this ensures nodes are active)
    bScn.use_nodes = True

    # Ensure compositor updates are enabled
    bScn.render.use_compositing = True
    bScn.render.use_sequencer = False  # Disable sequencer if not needed
    
    return
