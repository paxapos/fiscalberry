# src/main.py
import runpy
import os
import sys

try:
    # Set the current working directory to the script's directory
    # This helps ensure relative paths within your app work correctly
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Run your actual main script
    runpy.run_module('fiscalberry.gui', run_name='__main__')
    
except Exception as e:
    # Error crítico en el punto de entrada
    print(f"FATAL ERROR in main.py: {e}")
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