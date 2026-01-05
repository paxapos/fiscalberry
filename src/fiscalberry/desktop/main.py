from fiscalberry.ui.fiscalberry_app import FiscalberryApp
from fiscalberry.common.fiscalberry_logger import getLogger
import sys

logger = getLogger("GUI")

def main():
    """Función principal que ejecuta la interfaz gráfica de Fiscalberry."""
    logger.info("=== Iniciando Fiscalberry GUI ===")
    logger.info(f"Versión de Python: {sys.version}")
    logger.info(f"Plataforma: {sys.platform}")
    
    try:
        logger.info("Creando aplicación Kivy...")
        app = FiscalberryApp()
        logger.info("Iniciando aplicación GUI...")
        app.run()
        logger.info("Aplicación GUI finalizada correctamente")
    except Exception as e:
        logger.error(f"Error crítico en GUI: {e}", exc_info=True)
        raise
    finally:
        logger.info("=== Finalizando Fiscalberry GUI ===")

if __name__ == "__main__":
    main()