"""
El ícono de Fiscalberry en la bandeja del sistema (Windows).

Por qué existe: el servicio de impresión vive en hilos del mismo proceso que la
ventana. Cerrar la ventana con la X terminaba el proceso, y con él MQTT, el
websocket y el spooler: el local dejaba de imprimir hasta el próximo inicio de
sesión sin que nadie lo notara. Ahora la X oculta la ventana y Fiscalberry
sigue en la bandeja, que es desde donde se vuelve a abrir o se sale de verdad.

Este módulo no conoce a Kivy: recibe qué hacer al abrir y al salir. Los
callbacks corren en el hilo de la bandeja, así que quien los pasa tiene que
llevarlos al hilo de la interfaz si tocan la ventana.
"""

import importlib
import threading

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("GUI.Bandeja")

TITULO = "Fiscalberry"
TEXTO_ABRIR = "Abrir Fiscalberry"
TEXTO_SALIR = "Salir (deja de imprimir)"
AVISO_SEGUNDO_PLANO = (
    "Fiscalberry sigue imprimiendo en segundo plano. Para volver a abrirlo, "
    "tocá su ícono junto al reloj."
)
TITULO_CONFIRMAR_SALIDA = "Salir de Fiscalberry"
PREGUNTA_SALIR = (
    "Si salís, Fiscalberry deja de imprimir hasta que lo vuelvas a abrir.\n\n"
    "¿Querés salir igual?"
)

# Qué hacer cuando se pide cerrar la ventana.
IGNORAR = "ignorar"
OCULTAR = "ocultar"
MINIMIZAR = "minimizar"
SALIR = "salir"


def accion_al_cerrar(es_windows, bandeja_activa, origen=None):
    """
    Decide qué hace la X (o Alt+F4) según dónde corre y si hay bandeja.

    - Escape nunca cierra: en un local se toca todo el tiempo para cerrar
      diálogos del punto de venta.
    - Windows con bandeja: se oculta; el servicio sigue imprimiendo.
    - Windows sin bandeja (no se pudo crear el ícono): se minimiza. Ocultarla
      sin ícono la dejaría sin forma visible de volver a abrirla, y cerrarla
      dejaría de imprimir.
    - Resto de los sistemas: se cierra como siempre.
    """
    if origen == "keyboard":
        return IGNORAR
    if not es_windows:
        return SALIR
    return OCULTAR if bandeja_activa else MINIMIZAR


def confirmar_salida():
    """
    Pregunta con un cuadro nativo de Windows si salir de verdad.

    Es nativo y no un Popup de Kivy porque "Salir" se elige desde la bandeja,
    casi siempre con la ventana oculta.
    """
    import ctypes

    MB_YESNO = 0x00000004
    MB_ICONWARNING = 0x00000030
    MB_DEFBUTTON2 = 0x00000100
    MB_SETFOREGROUND = 0x00010000
    MB_TOPMOST = 0x00040000
    IDYES = 6

    respuesta = ctypes.windll.user32.MessageBoxW(
        None, PREGUNTA_SALIR, TITULO_CONFIRMAR_SALIDA,
        MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_SETFOREGROUND | MB_TOPMOST,
    )
    return respuesta == IDYES


class BandejaDelSistema:
    """
    Ícono con menú "Abrir Fiscalberry" (también con clic) y "Salir".

    `iniciar()` no bloquea: el ícono corre en su propio hilo. `activa` pasa a
    True recién cuando Windows lo muestra.
    """

    def __init__(self, al_abrir, al_salir, icono, confirmar=confirmar_salida,
                 pystray_mod=None):
        self._al_abrir = al_abrir
        self._al_salir = al_salir
        self._ruta_icono = icono
        self._confirmar = confirmar
        self._pystray = pystray_mod
        self._icono = None
        self._hilo = None
        self.activa = False

    def iniciar(self):
        """Crea el ícono en un hilo propio. Devuelve False si no se pudo."""
        try:
            pystray = self._pystray or importlib.import_module("pystray")
            imagen = self._cargar_imagen()
            menu = pystray.Menu(
                pystray.MenuItem(TEXTO_ABRIR, self._abrir, default=True),
                pystray.MenuItem(TEXTO_SALIR, self._salir),
            )
            self._icono = pystray.Icon("fiscalberry", imagen, TITULO, menu)
        except Exception as e:
            logger.warning("No se pudo crear el ícono de la bandeja: %s", e)
            return False

        self._hilo = threading.Thread(target=self._correr, daemon=True,
                                      name="fiscalberry-bandeja")
        self._hilo.start()
        return True

    def _cargar_imagen(self):
        from PIL import Image

        try:
            return Image.open(self._ruta_icono)
        except Exception as e:
            # Sin ícono propio, uno liso: mejor eso que quedarse sin bandeja.
            logger.warning("No se pudo cargar %s (%s); se usa un ícono liso.",
                           self._ruta_icono, e)
            return Image.new("RGBA", (64, 64), (176, 32, 80, 255))

    def _correr(self):
        def listo(icono):
            icono.visible = True
            self.activa = True
            logger.info("Ícono de Fiscalberry en la bandeja del sistema.")

        try:
            self._icono.run(setup=listo)
        except Exception as e:
            logger.error("La bandeja del sistema dejó de funcionar: %s", e)
        finally:
            self.activa = False

    def _abrir(self):
        try:
            self._al_abrir()
        except Exception as e:
            logger.error("No se pudo abrir la ventana desde la bandeja: %s", e)

    def _salir(self):
        try:
            if not self._confirmar():
                logger.info("Salir desde la bandeja: el usuario eligió no salir.")
                return
        except Exception as e:
            # Si no se puede preguntar, no se sale: dejar de imprimir por un
            # error del cuadro de diálogo sería peor que no poder salir.
            logger.error("No se pudo confirmar la salida (%s); no se sale.", e)
            return
        try:
            self._al_salir()
        except Exception as e:
            logger.error("Falló la salida desde la bandeja: %s", e)

    def avisar(self, mensaje, titulo=TITULO):
        """Notificación del sistema junto al ícono. Nunca lanza."""
        if not (self.activa and self._icono):
            return False
        try:
            self._icono.notify(mensaje, titulo)
            return True
        except Exception as e:
            logger.debug("No se pudo mostrar la notificación: %s", e)
            return False

    def detener(self, timeout=3.0):
        """Saca el ícono de la bandeja y espera a que termine su hilo."""
        if self._icono is not None:
            try:
                self._icono.stop()
            except Exception as e:
                logger.debug("Error deteniendo la bandeja: %s", e)
        if (self._hilo is not None and self._hilo.is_alive()
                and self._hilo is not threading.current_thread()):
            self._hilo.join(timeout)
        self.activa = False
