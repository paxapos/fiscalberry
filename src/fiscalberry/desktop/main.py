from fiscalberry.common.fiscalberry_logger import getLogger, setup_file_logging
from fiscalberry.common.updater.cli_modes import handle_early_modes
import sys
import threading

logger = getLogger("GUI")


def consume_start_minimized(argv=None):
    """Consume el argumento propio antes de que Kivy procese sys.argv."""
    argv = sys.argv if argv is None else argv
    if "--minimized" not in argv:
        return False
    argv.remove("--minimized")
    return True


class ActivationBridge:
    """
    Pedidos de "mostrá la ventana" que llegan de otras instancias.

    El listener arranca antes que Kivy (el acceso directo puede abrirse en
    cualquier momento), pero la ventana recién existe cuando la App corre. Si el
    pedido llega antes, queda pendiente y se atiende apenas la App se registra.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._handler = None
        self._pending = False

    def request_show(self):
        with self._lock:
            handler = self._handler
            if handler is None:
                self._pending = True
                return
        handler()

    def set_handler(self, handler):
        with self._lock:
            self._handler = handler
            pending, self._pending = self._pending, False
        if pending and handler is not None:
            handler()


activation = ActivationBridge()


def ensure_single_instance(acquire=None, request_activation=None, exit=sys.exit):
    """
    Una sola GUI por equipo: si ya hay una corriendo, le pide que se muestre y
    esta termina con código 0 (para el usuario, "abrir Fiscalberry" siempre
    trae la ventana existente).

    Se hace antes de importar Kivy: una segunda instancia no tiene que llegar a
    abrir otra ventana, ni otra conexión MQTT con el mismo client id.
    """
    from fiscalberry.common import single_instance

    acquire = acquire or single_instance.acquire_single_instance_lock
    request_activation = request_activation or single_instance.request_activation

    if acquire():
        return True

    if request_activation():
        logger.info("Fiscalberry ya estaba abierto: se mostró la ventana existente.")
    else:
        logger.warning("Fiscalberry ya está corriendo en este equipo; no se abre otra instancia.")
    exit(0)
    return False


def main():
    """Función principal que ejecuta la interfaz gráfica de Fiscalberry."""
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

    # Instancia única ANTES de todo lo demás: una segunda apertura no cuenta
    # como arranque de una actualización pendiente ni carga Kivy.
    ensure_single_instance()
    from fiscalberry.common.single_instance import start_activation_listener
    start_activation_listener(activation.request_show)

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

    from fiscalberry.desktop import tray
    if start_minimized and tray.is_supported():
        # La ventana se crea oculta: arrancar con Windows no tiene que tapar
        # la pantalla del local. Si la bandeja no llega a levantar, la App la
        # vuelve a mostrar (minimizada) para no dejarla inaccesible.
        tray.configure_hidden_window()

    try:
        # Import diferido: mantiene a Kivy fuera del camino de los modos
        # especiales de arriba.
        from fiscalberry.ui.fiscalberry_app import FiscalberryApp

        logger.info("Creando aplicación Kivy...")
        app = FiscalberryApp()
        app.start_minimized = start_minimized
        app.activation = activation
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
