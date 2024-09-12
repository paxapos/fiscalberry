#!/usr/bin/env python3
import os
import logging

from common.Configberry import Configberry

configberry = Configberry()

environment = configberry.config.get("SERVIDOR", "environment", fallback="production")


# Configuro logger según ambiente
if environment == 'development':
    print("* * * * * Modo de desarrollo * * * * *")
    logging.basicConfig(level=logging.DEBUG)
else:
    print("@ @ @ @ @ Modo de producción @ @ @ @ @")
    logging.basicConfig(level=logging.WARNING)


import sys


__version__ = "0.1.0"


if __name__ == "__main__":
    
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        import cli as cli

        cli.start()
        
    else:
        from ui.fiscalberry_app import FiscalberryApp

        # Llamar a la función que maneja la interfaz de usuario
        start_ui()
        # Crear la aplicación Kivy
        app = FiscalberryApp()

        # Ejecutar la aplicación Kivy
        app.run()
    
