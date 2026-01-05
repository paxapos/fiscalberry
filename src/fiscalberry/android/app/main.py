# src/fiscalberry/android/ui/main.py
"""
Android UI Entry Point

Este es el punto de entrada para la versión Android con UI (Kivy).
Reemplaza a src/main.py para mantener consistencia en la estructura.
"""
import runpy
import os
import sys

try:
    # Set the current working directory to the script's directory
    # This helps ensure relative paths within your app work correctly
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Run the desktop UI module (same UI for both platforms)
    runpy.run_module('fiscalberry.desktop.main', run_name='__main__')
    
except Exception as e:
    # Error crítico en el punto de entrada
    print(f"FATAL ERROR in android/ui/main.py: {e}")
    import traceback
    traceback.print_exc()
    
    # Intentar inicializar logging básico para debug
    try:
        with open('/sdcard/fiscalberry_crash.log', 'w') as f:
            f.write(f"FATAL ERROR: {e}\n")
            f.write(traceback.format_exc())
    except:
        pass
    
    sys.exit(1)
