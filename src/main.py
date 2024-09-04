#!/usr/bin/env python3
import os
import logging

from dotenv import load_dotenv
load_dotenv()

__version__ = "0.1.0"


# Configuro logger según ambiente
environment = os.getenv('ENVIRONMENT', 'production')
if environment == 'development':
    print("* * * * * Modo de desarrollo * * * * *")
    logging.basicConfig(level=logging.DEBUG)
else:
    print("@ @ @ @ @ Modo de producción @ @ @ @ @")
    logging.basicConfig(level=logging.WARNING)


from fiscalberry_app.fiscalberry_app import FiscalberryApp


if __name__ == "__main__":

    # Crear la aplicación Kivy
    app = FiscalberryApp()

    # Ejecutar la aplicación Kivy
    app.run()
