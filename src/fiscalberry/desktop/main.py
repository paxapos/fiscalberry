from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.updater.cli_modes import handle_early_modes
import sys

logger = getLogger("GUI")

def main():
    """Función principal que ejecuta la interfaz gráfica de Fiscalberry."""
    # Antes que nada: --selftest / --apply-update / --version no son arranques
    # normales y terminan el proceso acá. Va primero para que el ayudante de
    # actualización de Windows no tenga que cargar Kivy solo para copiar un
    # archivo.
    handle_early_modes()

    logger.info("=== Iniciando Fiscalberry GUI ===")
    logger.debug(f"Versión de Python: {sys.version}")
    logger.debug(f"Plataforma: {sys.platform}")

    # Reversión automática si la versión anterior se actualizó y nunca llegó a
    # confirmar el arranque. Tiene que correr antes de levantar nada.
    try:
        from fiscalberry.common.updater.service import on_process_start
        on_process_start()
    except Exception as e:
        logger.warning(f"No se pudo evaluar el estado de actualización: {e}")

    try:
        # Import diferido: mantiene a Kivy fuera del camino de los modos
        # especiales de arriba.
        from fiscalberry.ui.fiscalberry_app import FiscalberryApp

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
