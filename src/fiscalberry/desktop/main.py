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


def consume_start_minimized(argv=None):
    """Consume el argumento propio antes de que Kivy procese sys.argv."""
    argv = sys.argv if argv is None else argv
    if "--minimized" not in argv:
        return False
    argv.remove("--minimized")
    return True


# La app, una vez creada. El pedido de "mostrá la ventana" de una segunda
# instancia puede llegar antes (mientras se importa Kivy): en ese caso queda
# anotado y se atiende apenas exista la app.
_app = None
_mostrar_pendiente = False


def _pedido_de_mostrar_ventana():
    """Lo llama el hilo de activación cuando se abre Fiscalberry otra vez."""
    global _mostrar_pendiente
    app = _app
    if app is None:
        _mostrar_pendiente = True
        return
    app.mostrar_ventana()


def tomar_instancia_unica(start_minimized):
    """
    Decide si este proceso es EL Fiscalberry de la máquina.

    Si ya hay otro corriendo, le pide que muestre su ventana y devuelve False:
    abrir Fiscalberry desde el acceso directo o el menú Inicio retoma la
    instancia viva en vez de levantar una segunda que pelearía por el mismo
    client id MQTT y el mismo spooler. El arranque con la sesión
    (`--minimized`) no muestra nada: si ya hay uno abierto, no hace falta.
    """
    from fiscalberry.common import single_instance

    if single_instance.acquire_single_instance_lock():
        single_instance.start_activation_listener(_pedido_de_mostrar_ventana)
        return True

    if start_minimized:
        logger.info("Ya hay un Fiscalberry abierto: el arranque con la sesión "
                    "no abre otro.")
    elif single_instance.notify_running_instance():
        logger.info("Ya hay un Fiscalberry abierto: se muestra su ventana y "
                    "esta instancia termina.")
    else:
        logger.warning("Ya hay un Fiscalberry abierto, pero no respondió al "
                       "pedido de mostrar su ventana. Esta instancia termina.")
    return False


def _arrancar_sin_ventana():
    """
    Arranque con la sesión: la ventana no aparece.

    En Windows queda oculta y se abre desde el ícono de la bandeja. En el resto
    no hay bandeja, así que se minimiza: oculta no habría forma de abrirla.
    Tiene que correr antes de que Kivy cree la ventana.
    """
    from kivy.config import Config

    estado = "hidden" if sys.platform == "win32" else "minimized"
    Config.set("graphics", "window_state", estado)


def main():
    """Función principal que ejecuta la interfaz gráfica de Fiscalberry."""
    global _app

    # Antes que nada: --selftest / --apply-update / --version no son arranques
    # normales y terminan el proceso acá. Va primero para que el ayudante de
    # actualización de Windows no tenga que cargar Kivy solo para copiar un
    # archivo.
    handle_early_modes()
    start_minimized = consume_start_minimized()

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

    # Instancia única ANTES de contar el arranque y antes de cargar Kivy. Si
    # una segunda instancia llegara a on_process_start(), sumaría un arranque
    # sin confirmar a una actualización recién instalada: tres aperturas desde
    # el acceso directo bastaban para revertir una versión que andaba bien.
    if not tomar_instancia_unica(start_minimized):
        return

    # Reversión automática si la versión anterior se actualizó y nunca llegó a
    # confirmar el arranque. Tiene que correr antes de levantar nada.
    try:
        from fiscalberry.common.updater.service import on_process_start
        on_process_start()
    except Exception as e:
        logger.warning(f"No se pudo evaluar el estado de actualización: {e}")

    try:
        if start_minimized:
            _arrancar_sin_ventana()

        # Import diferido: mantiene a Kivy fuera del camino de los modos
        # especiales de arriba.
        from fiscalberry.ui.fiscalberry_app import FiscalberryApp

        logger.info("Creando aplicación Kivy...")
        app = FiscalberryApp()
        app.start_minimized = start_minimized
        _app = app
        if _mostrar_pendiente:
            app.mostrar_ventana()
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
