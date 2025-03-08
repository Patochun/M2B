import sys
import os
import importlib

def reloadProjectModules():
    """Reload all Python modules located in the project directory to reflect code changes without restarting Blender."""
    
    # Get the directory of the main script
    projectPath = os.path.dirname(__file__)  

    # Identify modules that belong to the project
    modulesToReload = [
        name for name, module in sys.modules.items()
        if hasattr(module, "__file__") and module.__file__ and module.__file__.startswith(projectPath)
    ]

    # Remove modules from cache
    for moduleName in modulesToReload:
        del sys.modules[moduleName]
        print(f"Module {moduleName} removed from cache")

    # Reload the modules
    for moduleName in modulesToReload:
        importlib.import_module(moduleName)
        print(f"Module {moduleName} reloaded")

