# coding=utf-8
"""
Bandeja del sistema y cierre de la ventana en Windows (#187).

El servicio de impresión vive en el mismo proceso que la ventana, así que lo
que se prueba acá es la promesa al usuario: la "X" nunca corta la impresión, y
salir de verdad solo pasa por "Salir (deja de imprimir)", con confirmación.
"""

import sys
import types

import pytest

from fiscalberry.desktop import tray
from fiscalberry.desktop.main import ActivationBridge, ensure_single_instance


# ---------------------------------------------------------------------------
# pystray de mentira
# ---------------------------------------------------------------------------

class MenuItemFalso:
    def __init__(self, text, action, default=False):
        self.text = text
        self.action = action
        self.default = default


class MenuFalso:
    SEPARATOR = MenuItemFalso("- - - -", None)

    def __init__(self, *items):
        self.items = items

    def item(self, texto):
        return next(i for i in self.items if i.text == texto)


class IconoFalso:
    def __init__(self, name, icon, title, menu):
        self.name = name
        self.icon = icon
        self.title = title
        self.menu = menu
        self.corriendo = False
        self.notificaciones = []
        self.detenido = False

    def run(self):
        self.corriendo = True

    def notify(self, mensaje, titulo):
        self.notificaciones.append((mensaje, titulo))

    def stop(self):
        self.detenido = True


class HiloSincronico:
    """Corre el target en el acto: el test no depende de hilos."""

    def __init__(self, target, daemon=None, name=None):
        self.target = target

    def start(self):
        self.target()


PYSTRAY = types.SimpleNamespace(Icon=IconoFalso, Menu=MenuFalso, MenuItem=MenuItemFalso)


class Registro:
    def __init__(self):
        self.abrir = 0
        self.salir = 0
        self.asistente = 0


def nueva_bandeja(registro, confirmar=lambda: True, con_asistente=False):
    return tray.TrayIcon(
        on_open=lambda: setattr(registro, "abrir", registro.abrir + 1),
        on_quit=lambda: setattr(registro, "salir", registro.salir + 1),
        on_setup=(lambda: setattr(registro, "asistente", registro.asistente + 1))
        if con_asistente else None,
        confirm=confirmar,
        pystray_module=PYSTRAY,
        thread_factory=HiloSincronico,
    )


# ---------------------------------------------------------------------------
# El ícono y su menú
# ---------------------------------------------------------------------------

def test_el_icono_corre_en_su_propio_hilo_con_el_menu_esperado():
    bandeja = nueva_bandeja(Registro())

    assert bandeja.start() is True

    icono = bandeja._icon
    assert icono.corriendo
    textos = [i.text for i in icono.menu.items if i is not MenuFalso.SEPARATOR]
    assert textos == [tray.MENU_OPEN, tray.MENU_QUIT]
    # Clic (y doble clic) sobre el ícono abre la ventana.
    assert icono.menu.item(tray.MENU_OPEN).default is True


def test_abrir_desde_la_bandeja():
    registro = Registro()
    bandeja = nueva_bandeja(registro)
    bandeja.start()

    bandeja._icon.menu.item(tray.MENU_OPEN).action(bandeja._icon, None)

    assert registro.abrir == 1


def test_salir_pide_confirmacion_y_si_se_cancela_sigue_imprimiendo():
    registro = Registro()
    preguntas = []

    def no_salir():
        preguntas.append(1)
        return False

    bandeja = nueva_bandeja(registro, confirmar=no_salir)
    bandeja.start()
    bandeja._icon.menu.item(tray.MENU_QUIT).action(bandeja._icon, None)

    assert preguntas == [1]
    assert registro.salir == 0


def test_salir_confirmado_detiene_todo():
    registro = Registro()
    bandeja = nueva_bandeja(registro, confirmar=lambda: True)
    bandeja.start()

    bandeja._icon.menu.item(tray.MENU_QUIT).action(bandeja._icon, None)

    assert registro.salir == 1


def test_si_la_confirmacion_falla_no_se_sale():
    def roto():
        raise OSError("sin user32")

    registro = Registro()
    bandeja = nueva_bandeja(registro, confirmar=roto)
    bandeja.start()
    bandeja._icon.menu.item(tray.MENU_QUIT).action(bandeja._icon, None)

    assert registro.salir == 0


def test_el_asistente_se_ofrece_si_hay_a_donde_llevar():
    registro = Registro()
    bandeja = nueva_bandeja(registro, con_asistente=True)
    bandeja.start()

    bandeja._icon.menu.item(tray.MENU_SETUP).action(bandeja._icon, None)

    assert registro.asistente == 1


def test_notificacion_y_estado_en_el_tooltip():
    bandeja = nueva_bandeja(Registro())
    bandeja.start()

    assert bandeja.notify(tray.BACKGROUND_NOTICE) is True
    bandeja.set_status("Listo para imprimir")

    assert bandeja._icon.notificaciones == [(tray.BACKGROUND_NOTICE, tray.TRAY_TITLE)]
    assert bandeja._icon.title == "Fiscalberry - Listo para imprimir"


def test_si_pystray_falla_no_hay_bandeja():
    def icono_roto(*args, **kwargs):
        raise RuntimeError("sin shell")

    modulo = types.SimpleNamespace(Icon=icono_roto, Menu=MenuFalso, MenuItem=MenuItemFalso)
    bandeja = tray.TrayIcon(on_open=lambda: None, on_quit=lambda: None,
                            pystray_module=modulo, thread_factory=HiloSincronico)

    assert bandeja.start() is False
    assert bandeja.running is False
    assert bandeja.notify("x") is False


def test_detener_quita_el_icono():
    bandeja = nueva_bandeja(Registro())
    bandeja.start()
    icono = bandeja._icon

    bandeja.stop()

    assert icono.detenido
    assert bandeja.running is False


@pytest.mark.parametrize("plataforma,importa,esperado", [
    ("linux", True, False),
    ("win32", True, True),
    ("win32", False, False),
])
def test_bandeja_solo_en_windows_con_pystray(plataforma, importa, esperado):
    def importer():
        if not importa:
            raise ImportError("pystray")
        return PYSTRAY

    assert tray.is_supported(platform=plataforma, importer=importer) is esperado


# ---------------------------------------------------------------------------
# Segunda apertura: se muestra la ventana existente y se sale con 0
# ---------------------------------------------------------------------------

def test_con_el_candado_libre_la_gui_arranca():
    salidas = []
    assert ensure_single_instance(acquire=lambda: True,
                                  request_activation=lambda: pytest.fail("no"),
                                  exit=salidas.append) is True
    assert salidas == []


@pytest.mark.parametrize("activada", [True, False])
def test_con_otra_instancia_se_activa_y_sale_con_cero(activada):
    pedidos = []
    salidas = []

    def activar():
        pedidos.append(1)
        return activada

    ensure_single_instance(acquire=lambda: False, request_activation=activar,
                           exit=salidas.append)

    assert pedidos == [1]
    assert salidas == [0]


def test_un_pedido_antes_de_que_exista_la_ventana_queda_pendiente():
    puente = ActivationBridge()
    mostradas = []

    puente.request_show()
    assert mostradas == []

    puente.set_handler(lambda: mostradas.append(1))
    assert mostradas == [1]

    puente.request_show()
    assert mostradas == [1, 1]


# ---------------------------------------------------------------------------
# La "X" de la ventana (FiscalberryApp)
# ---------------------------------------------------------------------------

class VentanaFalsa:
    def __init__(self):
        self.llamadas = []

    def hide(self):
        self.llamadas.append("hide")

    def show(self):
        self.llamadas.append("show")

    def restore(self):
        self.llamadas.append("restore")

    def raise_window(self):
        self.llamadas.append("raise")

    def minimize(self):
        self.llamadas.append("minimize")


@pytest.fixture
def ventana(monkeypatch):
    v = VentanaFalsa()
    monkeypatch.setitem(sys.modules, "kivy.core.window",
                        types.SimpleNamespace(Window=v))
    return v


@pytest.fixture
def app_cls():
    from fiscalberry.ui.fiscalberry_app import FiscalberryApp
    return FiscalberryApp


class AppFalsa:
    """Lo mínimo de FiscalberryApp para probar sus métodos sin levantar Kivy."""

    def __init__(self, app_cls, bandeja):
        self._tray = bandeja
        self._tray_notified = False
        self.salidas = 0
        self._cls = app_cls

    def hide_to_tray(self):
        return self._cls.hide_to_tray(self)

    def _immediate_force_exit_standalone(self):
        self.salidas += 1


def test_la_x_oculta_la_ventana_y_no_termina_el_proceso(app_cls, ventana):
    bandeja = nueva_bandeja(Registro())
    bandeja.start()
    app = AppFalsa(app_cls, bandeja)

    assert app_cls._on_window_close(app) is True

    assert ventana.llamadas == ["hide"]
    assert app.salidas == 0
    # La primera vez se avisa que sigue imprimiendo.
    assert bandeja._icon.notificaciones == [(tray.BACKGROUND_NOTICE, tray.TRAY_TITLE)]


def test_el_aviso_de_segundo_plano_sale_una_sola_vez(app_cls, ventana):
    bandeja = nueva_bandeja(Registro())
    bandeja.start()
    app = AppFalsa(app_cls, bandeja)

    app_cls._on_window_close(app)
    app_cls._on_window_close(app)

    assert ventana.llamadas == ["hide", "hide"]
    assert len(bandeja._icon.notificaciones) == 1


def test_la_tecla_escape_tambien_oculta(app_cls, ventana):
    """Kivy manda on_request_close(source='keyboard') al apretar Escape."""
    bandeja = nueva_bandeja(Registro())
    bandeja.start()
    app = AppFalsa(app_cls, bandeja)

    assert app_cls._on_window_close(app, source="keyboard") is True
    assert ventana.llamadas == ["hide"]


def test_sin_bandeja_la_x_cierra_como_siempre(app_cls, ventana):
    """Linux, o Windows sin pystray: comportamiento anterior."""
    app = AppFalsa(app_cls, None)

    app_cls._on_window_close(app)

    assert app.salidas == 1
    assert ventana.llamadas == []


def test_mostrar_la_ventana_la_trae_al_frente(app_cls, ventana):
    app_cls.show_window(object())
    assert ventana.llamadas == ["show", "restore", "raise"]


def test_sin_bandeja_el_arranque_minimizado_vuelve_a_mostrar_la_ventana(app_cls, ventana):
    """
    Si la ventana se pidió oculta y la bandeja no levantó, quedaría
    inaccesible: se muestra y se minimiza, como antes de la bandeja.
    """
    app_cls._minimize_windows(object(), 0)
    assert ventana.llamadas == ["show", "minimize"]
