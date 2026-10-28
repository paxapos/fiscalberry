# coding=utf-8
"""
Cómo se cierra la ventana de la app de escritorio.

Casos reales (Windows, 3.6.6):

1. Tocar Escape con la ventana de Fiscalberry enfocada tumbaba la app:
       TypeError: FiscalberryApp._on_window_close() got an unexpected keyword
       argument 'source'
   Kivy despacha `on_request_close(source="keyboard")` al tocar Escape
   (exit_on_escape=1 por defecto) y el handler no aceptaba kwargs.
2. Cerrar con la X / Alt+F4 / "Finalizar tarea" hacía `os._exit(0)` sin una
   línea en el log: al diagnosticar, un cierre hecho por alguien era
   indistinguible de un crash.

Se usa el despacho de eventos REAL de Kivy (EventDispatcher), que es el que
reenvía el `source=` a los handlers.
"""

import logging

import pytest

pytest.importorskip("kivy")

from kivy.config import Config  # noqa: E402
from kivy.event import EventDispatcher  # noqa: E402

from fiscalberry.ui.fiscalberry_app import FiscalberryApp  # noqa: E402


class VentanaFalsa(EventDispatcher):
    """Lo mínimo de una Window de Kivy: el evento on_request_close."""

    def __init__(self, **kwargs):
        self.register_event_type("on_request_close")
        super().__init__(**kwargs)

    def on_request_close(self, *args, **kwargs):
        return False


class AppFalsa:
    """El handler solo usa self para salir; no hace falta levantar la App."""

    def __init__(self):
        self.salidas = 0

    def _immediate_force_exit_standalone(self):
        self.salidas += 1


def _ventana_con_handler():
    app = AppFalsa()
    ventana = VentanaFalsa()
    ventana.bind(on_request_close=lambda *a, **kw:
                 FiscalberryApp._on_window_close(app, *a, **kw))
    return app, ventana


def test_escape_no_esta_habilitado_para_cerrar():
    assert Config.getint("kivy", "exit_on_escape") == 0


def test_escape_no_tumba_ni_cierra_la_app(caplog):
    app, ventana = _ventana_con_handler()

    with caplog.at_level(logging.INFO):
        cancelado = ventana.dispatch("on_request_close", source="keyboard")

    assert cancelado is True
    assert app.salidas == 0


def test_cerrar_con_la_x_sale_y_queda_en_el_log(caplog):
    app, ventana = _ventana_con_handler()

    with caplog.at_level(logging.WARNING):
        ventana.dispatch("on_request_close")

    assert app.salidas == 1
    assert "Ventana cerrada por el usuario" in caplog.text


def test_el_handler_viejo_reproduce_el_typeerror():
    """Fija el mecanismo del bug: Kivy SÍ reenvía source= a los handlers."""
    def handler_viejo(*args):
        return True

    ventana = VentanaFalsa()
    ventana.bind(on_request_close=handler_viejo)

    with pytest.raises(TypeError, match="source"):
        ventana.dispatch("on_request_close", source="keyboard")



# --------------------------------------------------------------------------
# Windows: la X oculta la ventana en la bandeja y el servicio sigue
# --------------------------------------------------------------------------

class VentanaKivyFalsa:
    def __init__(self):
        self.ocultada = 0
        self.minimizada = 0

    def hide(self):
        self.ocultada += 1

    def minimize(self):
        self.minimizada += 1


class BandejaFalsa:
    def __init__(self, activa=True):
        self.activa = activa
        self.avisos = []

    def avisar(self, mensaje):
        self.avisos.append(mensaje)
        return True


class AppWindows(AppFalsa):
    def __init__(self, bandeja):
        super().__init__()
        self._bandeja = bandeja
        self._is_android = False
        self.ventana = VentanaKivyFalsa()

    def _ventana(self):
        return self.ventana


@pytest.fixture
def en_windows(monkeypatch):
    import fiscalberry.ui.fiscalberry_app as modulo
    monkeypatch.setattr(modulo.sys, "platform", "win32")


def test_en_windows_la_x_oculta_y_no_sale(en_windows, caplog):
    app = AppWindows(BandejaFalsa())

    with caplog.at_level(logging.INFO):
        cancelado = FiscalberryApp._on_window_close(app)

    assert cancelado is True
    assert app.salidas == 0
    assert app.ventana.ocultada == 1
    assert "sigue imprimiendo" in caplog.text


def test_el_aviso_de_segundo_plano_sale_una_sola_vez(en_windows):
    from fiscalberry.desktop import tray

    bandeja = BandejaFalsa()
    app = AppWindows(bandeja)

    FiscalberryApp._on_window_close(app)
    FiscalberryApp._on_window_close(app)

    assert app.ventana.ocultada == 2
    assert bandeja.avisos == [tray.AVISO_SEGUNDO_PLANO]


def test_sin_bandeja_la_x_minimiza_en_vez_de_cerrar(en_windows):
    app = AppWindows(BandejaFalsa(activa=False))

    FiscalberryApp._on_window_close(app)

    assert app.salidas == 0
    assert app.ventana.minimizada == 1
    assert app.ventana.ocultada == 0
