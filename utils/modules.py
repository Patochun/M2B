import sys
import os
import importlib

def reloadProjectModules():
    """Reload all Python modules from M2B project directory."""
    
    # Get absolute path to M2B root directory
    m2b_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # Add M2B root to Python path if not already there
    if m2b_root not in sys.path:
        sys.path.append(m2b_root)

    # Define project packages to reload
    m2b_packages = [
        'config',
        'utils',
        'animations'
    ]

    # Identify and reload M2B modules
    for module_name, module in list(sys.modules.items()):
        if module is None:
            continue
            
        # Check if module belongs to M2B project
        is_m2b_module = any(
            module_name.startswith(pkg) or 
            module_name == pkg 
            for pkg in m2b_packages
        )
        
        if is_m2b_module:
            try:
                importlib.reload(module)
                print(f"[M2B] Reloaded: {module_name}")
            except Exception as error:
                print(f"[M2B] Failed to reload {module_name}: {error}")
                