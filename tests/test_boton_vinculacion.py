# coding=utf-8
"""
El botón "Abrir vinculación" tiene que abrir el link, igual que el QR (#191).

Caso real: en las versiones GUI el botón mostraba "No se pudo registrar el
dispositivo en el servidor" y no abría nada; escaneando el QR —mismo link— la
adopción funcionaba. El botón reenviaba el discover en el hilo de Kivy (UI
congelada hasta 30 s) porque nunca se enteraba del discover del arranque, y si
ese segundo intento fallaba se negaba a abrir el link, aunque el dispositivo ya
estuviera registrado.
"""

import sys
import threading
import types

import pytest

pytest.importorskip("requests")


def _instalar_kivy_de_mentira():
    """Lo mínimo de Kivy que usa adopt_screen, para correr sin Kivy instalado."""

    class Screen:
        manager = None

        def __init__(self, **kwargs):
            self.name = kwargs.get("name", "")

    def propiedad(valor=None, *a, **kw):
        return valor

    modulos = {
        "kivy": types.ModuleType("kivy"),
        "kivy.uix": types.ModuleType("kivy.uix"),
        "kivy.uix.screenmanager": types.ModuleType("kivy.uix.screenmanager"),
        "kivy.app": types.ModuleType("kivy.app"),
        "kivy.clock": types.ModuleType("kivy.clock"),
        "kivy.properties": types.ModuleType("kivy.properties"),
    }
    modulos["kivy.uix.screenmanager"].Screen = Screen
    modulos["kivy.app"].App = type("App", (), {"get_running_app": staticmethod(lambda: None)})
    modulos["kivy.clock"].Clock = types.SimpleNamespace(schedule_once=lambda fn, t=0: fn(0))
    modulos["kivy.properties"].StringProperty = propiedad
    modulos["kivy.properties"].BooleanProperty = propiedad
    sys.modules.update(modulos)


try:
    import kivy  # noqa: F401
except ImportError:
    _instalar_kivy_de_mentira()

from fiscalberry.common import discover  # noqa: E402
from fiscalberry.ui import adopt_screen  # noqa: E402

URL = "https://beta.paxapos.com/adopt/263ae979-f969-4630-bc49-3bb44e04f86c"


class Navegador:
    def __init__(self, abre=True):
        self.abre = abre
        self.abiertos = []

    def open(self, url):
        self.abiertos.append(url)
        return self.abre


@pytest.fixture
def navegador(monkeypatch):
    import webbrowser

    nav = Navegador()
    monkeypatch.setattr(webbrowser, "open", nav.open)
    return nav


@pytest.fixture
def pantalla(monkeypatch):
    # El resultado del hilo vuelve a la UI por Clock: en los tests, en el acto.
    monkeypatch.setattr(adopt_screen, "Clock",
                        types.SimpleNamespace(schedule_once=lambda fn, t=0: fn(0)))
    monkeypatch.setattr(adopt_screen, "ANDROID_AVAILABLE", False)
    p = adopt_screen.AdoptScreen(name="adopt")
    p.adoptarLink = URL
    return p


def _discover(monkeypatch, resultado, llamadas):
    def falso():
        llamadas.append(threading.current_thread())
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    monkeypatch.setattr(discover, "send_discover", falso)


def _click(pantalla):
    pantalla.open_adoption_link()
    if pantalla._registro_thread is not None:
        pantalla._registro_thread.join(timeout=5)


def test_registrado_al_arrancar_abre_sin_repetir_el_discover(pantalla, navegador, monkeypatch):
    llamadas = []
    _discover(monkeypatch, True, llamadas)

    pantalla.marcar_registrado(True)
    _click(pantalla)

    assert navegador.abiertos == [URL]
    assert llamadas == []


@pytest.mark.parametrize("fallo", [False, RuntimeError("timeout")])
def test_si_el_discover_falla_el_link_se_abre_igual(pantalla, navegador, monkeypatch, fallo):
    """El bug de #191: un discover fallido no puede bloquear la adopción."""
    _discover(monkeypatch, fallo, [])

    _click(pantalla)

    assert navegador.abiertos == [URL]
    assert pantalla.linkError  # queda el aviso a la vista
    assert pantalla.registrando is False


def test_el_discover_no_corre_en_el_hilo_de_la_ui(pantalla, navegador, monkeypatch):
    """Con timeout de 30 s, correrlo en el hilo de Kivy congela la ventana."""
    llamadas = []
    _discover(monkeypatch, True, llamadas)

    _click(pantalla)

    assert len(llamadas) == 1
    assert llamadas[0] is not threading.current_thread()
    assert navegador.abiertos == [URL]
    assert pantalla.linkError == ""


def test_con_registro_exitoso_el_segundo_click_no_repite_el_discover(pantalla, navegador, monkeypatch):
    llamadas = []
    _discover(monkeypatch, True, llamadas)

    _click(pantalla)
    _click(pantalla)

    assert len(llamadas) == 1
    assert navegador.abiertos == [URL, URL]


def test_doble_click_mientras_registra_no_lanza_otro_discover(pantalla, navegador, monkeypatch):
    llamadas = []
    liberar = threading.Event()

    def lento():
        llamadas.append(1)
        liberar.wait(5)
        return True

    monkeypatch.setattr(discover, "send_discover", lento)

    pantalla.open_adoption_link()
    hilo = pantalla._registro_thread
    assert pantalla.registrando is True
    pantalla.open_adoption_link()  # segundo click, con el primero en curso
    liberar.set()
    hilo.join(timeout=5)

    assert len(llamadas) == 1
    assert navegador.abiertos == [URL]


def test_si_no_se_puede_abrir_el_navegador_lo_dice_en_pantalla(pantalla, navegador, monkeypatch):
    navegador.abre = False
    pantalla.marcar_registrado(True)

    _click(pantalla)

    assert URL in pantalla.linkError
    assert "QR" in pantalla.linkError


def test_link_sin_uuid_no_se_abre(pantalla, navegador, monkeypatch):
    llamadas = []
    _discover(monkeypatch, True, llamadas)
    pantalla.adoptarLink = "https://beta.paxapos.com/adopt/"

    _click(pantalla)

    assert navegador.abiertos == []
    assert llamadas == []
    assert pantalla.linkError
