# src/main_headless.py
"""
Android Headless Entry Point

Buildozer requires main.py in the root of source.dir.
Redirects to the Android Headless entry point.
"""
import runpy
import os
import sys

try:
    src_dir = os.path.dirname(os.path.abspath(__file__))
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    
    runpy.run_module('fiscalberry.android.headless.main', run_name='__main__')
    
except Exception as e:
    print(f"FATAL ERROR in main_headless.py: {e}")
    import traceback
    traceback.print_exc()
    
    try:
        with open('/sdcard/fiscalberry_cli_crash.log', 'w') as f:
            f.write(f"FATAL ERROR: {e}\n")
            f.write(traceback.format_exc())
    except:
        pass
    
    sys.exit(1)
