#!/usr/bin/env python3
import sys

from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger("CLI")
from fiscalberry.common.service_controller import ServiceController

def main():
    """Función principal que ejecuta el controlador de servicios."""
    logger.info("=== Iniciando Fiscalberry CLI ===")
    logger.info(f"Versión de Python: {sys.version}")
    logger.info(f"Plataforma: {sys.platform}")
    
    controller = ServiceController()
    
    try:
        logger.info("Iniciando controlador de servicios...")
        controller.start()
        logger.info("Controlador de servicios iniciado exitosamente")
    except KeyboardInterrupt:
        logger.info("Interrupción de teclado detectada por usuario")
        print("\nInterrupción de teclado detectada. Cerrando servicios...")
        try:
            controller.stop()
            logger.info("Servicios detenidos correctamente")
        except Exception as stop_error:
            logger.error(f"Error al detener servicios: {stop_error}")
        print("Servicio detenido. Saliendo.")
    except Exception as e:
        logger.error(f"Error inesperado en CLI: {e}", exc_info=True)
        print(f"Error inesperado: {e}")
        try:
            controller.stop()
            logger.info("Servicios detenidos después de error")
        except Exception as stop_error:
            logger.error(f"Error al detener servicios después de excepción: {stop_error}")
        sys.exit(1)
    finally:
        logger.info("=== Finalizando Fiscalberry CLI ===")
        sys.exit(0)

if __name__ == "__main__":
    main()

