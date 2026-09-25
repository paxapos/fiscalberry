from fiscalberry.common.fiscalberry_logger import getLogger, setup_file_logging
from fiscalberry.common.updater.cli_modes import handle_early_modes
import sys

logger = getLogger("GUI")

# Se mantiene abierto mientras viva el proceso: faulthandler escribe ahí
# directamente desde C, justo cuando Python ya no puede loguear nada.
_crash_file = None


def _registrar_crashes():
    """
    Deja rastro de lo que hoy termina el proceso sin dejar nada en el log.

    - Un crash nativo (access violation en un driver o en una DLL) no pasa por
      Python: sin faulthandler, el log simplemente se corta. Con esto queda en
      logs/crash.log la pila de cada hilo en el momento del crash.
    - Una excepción no manejada en un hilo se imprime a stderr, que en el .exe
      sin consola no existe: se pierde. Se manda al log.
    """
    global _crash_file
    try:
        import faulthandler
        import os
        from fiscalberry.common.fiscalberry_logger import getServiceLogFilePath

        ruta_log = getServiceLogFilePath()
        if ruta_log:
            ruta = os.path.join(os.path.dirname(ruta_log), "crash.log")
            _crash_file = open(ruta, "a", encoding="utf-8")
            faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception as e:
        logger.warning(f"No se pudo activar el registro de crashes: {e}")

    try:
        import threading

        def _excepcion_en_hilo(args):
            if issubclass(args.exc_type, SystemExit):
                return
            nombre = args.thread.name if args.thread else "?"
            logger.error(f"Excepción no manejada en el hilo {nombre}",
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

        threading.excepthook = _excepcion_en_hilo
    except Exception as e:
        logger.warning(f"No se pudo registrar las excepciones de hilos: {e}")

def main():
    """Función principal que ejecuta la interfaz gráfica de Fiscalberry."""
    # Antes que nada: --selftest / --apply-update / --version no son arranques
    # normales y terminan el proceso acá. Va primero para que el ayudante de
    # actualización de Windows no tenga que cargar Kivy solo para copiar un
    # archivo.
    handle_early_modes()

    # El log en archivo se prende acá y no recién al importar la app Kivy: el
    # .exe de Windows corre sin consola, así que sin archivo los mensajes de
    # este arranque temprano —justo los que hacen falta cuando la GUI ni
    # aparece— no quedan en ningún lado. El rol es el mismo que usa
    # ui/fiscalberry_app.py: es el mismo proceso, y como setup_file_logging es
    # idempotente, la primera llamada es la que fija el rol del archivo.
    setup_file_logging(role="app")
    _registrar_crashes()

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
