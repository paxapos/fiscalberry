"""
Ícono de Fiscalberry en la bandeja del sistema (Windows).

El servicio de impresión vive en hilos del mismo proceso que la ventana: si la
"X" cerrara el proceso, el local dejaría de imprimir hasta el próximo inicio de
sesión. Por eso en Windows la "X" solo oculta la ventana, y lo que queda a la
vista es este ícono junto al reloj:

- "Abrir Fiscalberry" (también con clic sobre el ícono) vuelve a mostrar la
  ventana.
- "Salir (deja de imprimir)" pide confirmación y recién ahí detiene todo.

pystray corre su propio loop de mensajes en un hilo aparte, independiente del
de Kivy: las acciones del menú llegan desde ese hilo y la App las pasa al hilo
principal. Todo lo que toca Windows es inyectable para poder probarlo sin él.
"""

import os
import sys
import threading

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("GUI.Tray")

TRAY_TITLE = "Fiscalberry"
BACKGROUND_NOTICE = "Fiscalberry sigue imprimiendo en segundo plano"
QUIT_QUESTION = (
    "Si salís, Fiscalberry deja de imprimir hasta que lo vuelvas a abrir.\n\n"
    "¿Querés salir igual?"
)

MENU_OPEN = "Abrir Fiscalberry"
MENU_SETUP = "Configurar impresoras"
MENU_QUIT = "Salir (deja de imprimir)"


def _import_pystray():
    import pystray
    return pystray


def is_supported(platform=None, importer=_import_pystray):
    """La bandeja se usa solo en Windows y solo si pystray está disponible."""
    platform = sys.platform if platform is None else platform
    if platform != "win32":
        return False
    try:
        importer()
    except Exception as e:
        logger.warning(f"Bandeja no disponible (pystray): {e}")
        return False
    return True


def configure_hidden_window():
    """
    Pide a Kivy que cree la ventana oculta (arranque con Windows).

    Tiene que llamarse antes de que se importe kivy.core.window: la ventana se
    crea con el estado que diga la configuración en ese momento.
    """
    try:
        from kivy.config import Config
        Config.set("graphics", "window_state", "hidden")
    except Exception as e:
        logger.warning(f"No se pudo pedir la ventana oculta: {e}")


def confirm_quit_windows(message=QUIT_QUESTION, title=TRAY_TITLE):
    """Cartel nativo Sí/No: la ventana de Kivy puede estar oculta."""
    import ctypes

    MB_YESNO = 0x04
    MB_ICONWARNING = 0x30
    MB_DEFBUTTON2 = 0x100
    MB_SETFOREGROUND = 0x10000
    MB_TOPMOST = 0x40000
    IDYES = 6
    flags = MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_SETFOREGROUND | MB_TOPMOST
    return ctypes.windll.user32.MessageBoxW(None, message, title, flags) == IDYES


def _load_image(icon_path):
    from PIL import Image
    return Image.open(icon_path)


class TrayIcon:
    """
    El ícono de la bandeja y su menú.

    `on_open`, `on_setup` y `on_quit` se llaman desde el hilo de pystray.
    `on_setup` es opcional: si no se pasa, el menú no ofrece el asistente.
    """

    def __init__(self, on_open, on_quit, on_setup=None, icon_path=None,
                 confirm=confirm_quit_windows, pystray_module=None,
                 image_loader=_load_image, thread_factory=threading.Thread):
        self._on_open = on_open
        self._on_quit = on_quit
        self._on_setup = on_setup
        self._icon_path = icon_path
        self._confirm = confirm
        self._pystray = pystray_module
        self._image_loader = image_loader
        self._thread_factory = thread_factory
        self._icon = None
        self._thread = None

    @property
    def running(self):
        return self._icon is not None

    def _menu(self, pystray):
        items = [pystray.MenuItem(MENU_OPEN, self._open_clicked, default=True)]
        if self._on_setup is not None:
            items.append(pystray.MenuItem(MENU_SETUP, self._setup_clicked))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem(MENU_QUIT, self._quit_clicked))
        return pystray.Menu(*items)

    def start(self):
        """Muestra el ícono. Devuelve False si no se pudo (la App no oculta)."""
        if self._icon is not None:
            return True
        try:
            pystray = self._pystray or _import_pystray()
            image = None
            if self._icon_path and os.path.exists(self._icon_path):
                image = self._image_loader(self._icon_path)
            icon = pystray.Icon("fiscalberry", image, TRAY_TITLE, self._menu(pystray))
            thread = self._thread_factory(target=icon.run, daemon=True,
                                          name="fiscalberry-tray")
            thread.start()
        except Exception as e:
            logger.error(f"No se pudo mostrar el ícono de la bandeja: {e}", exc_info=True)
            return False
        self._icon = icon
        self._thread = thread
        logger.info("Ícono de la bandeja activo")
        return True

    def stop(self):
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception as e:
                logger.debug(f"Error cerrando el ícono de la bandeja: {e}")

    def notify(self, message, title=TRAY_TITLE):
        if self._icon is None:
            return False
        try:
            self._icon.notify(message, title)
            return True
        except Exception as e:
            logger.debug(f"No se pudo mostrar la notificación: {e}")
            return False

    def set_status(self, text):
        """Tooltip del ícono: el estado se ve sin abrir la ventana."""
        if self._icon is None:
            return
        try:
            self._icon.title = f"{TRAY_TITLE} - {text}" if text else TRAY_TITLE
        except Exception as e:
            logger.debug(f"No se pudo actualizar el tooltip de la bandeja: {e}")

    # -- acciones del menú (hilo de pystray) --------------------------------

    def _open_clicked(self, *_):
        self._on_open()

    def _setup_clicked(self, *_):
        if self._on_setup is not None:
            self._on_setup()

    def _quit_clicked(self, *_):
        try:
            confirmed = self._confirm()
        except Exception as e:
            logger.error(f"No se pudo pedir confirmación para salir: {e}")
            confirmed = False
        if confirmed:
            logger.info("Salida pedida desde la bandeja")
            self._on_quit()
