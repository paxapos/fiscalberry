#!/usr/bin/env python3
import sys
import os

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fiscalberry.common.service_controller import ServiceController

def test_mode_detection():
    controller = ServiceController()
    
    print("Probando detección de modo...")
    is_gui = controller._is_gui_mode()
    print(f"¿Es modo GUI? {is_gui}")
    
    if is_gui:
        print("Modo GUI detectado - usará stop_for_gui()")
    else:
        print("Modo CLI detectado - usará stop_for_cli()")

if __name__ == "__main__":
    test_mode_detection()
