#!/usr/bin/env python3
import sys

from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger()
from fiscalberry.common.service_controller import ServiceController

def main():
    """Función principal que ejecuta el controlador de servicios."""
    controller = ServiceController()
    
    try:
        controller.start()
    except KeyboardInterrupt:
        print("\nInterrupción de teclado detectada. Cerrando servicios...")
        controller.stop()
        print("Servicio detenido. Saliendo.")
    except Exception as e:
        print(f"Error inesperado: {e}")
        controller.stop()
        sys.exit(1)

if __name__ == "__main__":
    main()

