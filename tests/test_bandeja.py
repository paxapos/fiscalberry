# coding=utf-8
"""
La bandeja del sistema en Windows.

El servicio de impresión vive en el mismo proceso que la ventana: cerrar la
ventana con la X cortaba MQTT, el websocket y el spooler, y el local dejaba de
imprimir sin que nadie lo notara. La X ahora la oculta en la bandeja, y desde
ahí se vuelve a abrir o se sale de verdad, con confirmación.

pystray se reemplaza por un módulo falso: estos tests corren en Linux.
"""

import threading
import time
import types

import pytest

from fiscalberry.desktop import tray


# --------------------------------------------------------------------------
# Qué hace la X
# --------------------------------------------------------------------------

@pytest.mark.parametrize("es_windows,bandeja,origen,esperado", [
    (True, True, None, tray.OCULTAR),
    (True, False, None, tray.MINIMIZAR),
    (False, False, None, tray.SALIR),
    (True, True, "keyboard", tray.IGNORAR),
    (False, False, "keyboard", tray.IGNORAR),
])
def test_accion_al_cerrar(es_windows, bandeja, origen, esperado):
    assert tray.accion_al_cerrar(es_windows, bandeja, origen) == esperado


# --------------------------------------------------------------------------
# El ícono
# --------------------------------------------------------------------------

def _pystray_falso():
    mod = types.SimpleNamespace(iconos=[])

    class MenuItem:
        def __init__(self, texto, accion, default=False):
            self.texto, self.accion, self.default = texto, accion, default

    class Menu:
        def __init__(self, *items):
            self.items = items

    class Icon:
        def __init__(self, nombre, imagen, titulo, menu):
            self.nombre, self.imagen, self.titulo, self.menu = nombre, imagen, titulo, menu
            self.visible = False
            self.avisos = []
            self._parar = threading.Event()
            mod.iconos.append(self)

        def run(self, setup=None):
            setup(self)
            self._parar.wait(5)

        def stop(self):
            self._parar.set()

        def notify(self, mensaje, titulo=None):
            self.avisos.append((mensaje, titulo))

        def item(self, texto):
            return next(i for i in self.menu.items if i.texto == texto)

    mod.MenuItem, mod.Menu, mod.Icon = MenuItem, Menu, Icon
    return mod


class Registro:
    def __init__(self, confirma=True):
        self.abiertas = 0
        self.salidas = 0
        self.confirma = confirma
        self.preguntas = 0

    def abrir(self):
        self.abiertas += 1

    def salir(self):
        self.salidas += 1

    def confirmar(self):
        self.preguntas += 1
        return self.confirma


def _esperar(condicion, timeout=3.0):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.02)
    return condicion()


@pytest.fixture
def bandeja_falsa(tmp_path):
    reg = Registro()
    mod = _pystray_falso()
    bandeja = tray.BandejaDelSistema(
        al_abrir=reg.abrir, al_salir=reg.salir,
        icono=str(tmp_path / "no-existe.ico"),
        confirmar=reg.confirmar, pystray_mod=mod)
    yield bandeja, reg, mod
    bandeja.detener()


def test_el_menu_abre_y_sale_con_los_textos_para_el_usuario(bandeja_falsa):
    bandeja, reg, mod = bandeja_falsa
    assert bandeja.iniciar() is True
    assert _esperar(lambda: bandeja.activa)

    icono = mod.iconos[0]
    assert icono.visible is True
    abrir = icono.item(tray.TEXTO_ABRIR)
    salir = icono.item(tray.TEXTO_SALIR)
    # Abrir es la acción por defecto: la que dispara el clic sobre el ícono.
    assert abrir.default is True and salir.default is False
    assert "deja de imprimir" in salir.texto

    abrir.accion()
    assert reg.abiertas == 1


def test_sin_asistente_el_menu_no_ofrece_configurar_impresoras(bandeja_falsa):
    bandeja, _, mod = bandeja_falsa
    assert bandeja.iniciar()
    textos = [i.texto for i in mod.iconos[0].menu.items]
    assert textos == [tray.TEXTO_ABRIR, tray.TEXTO_SALIR]


def test_con_asistente_el_menu_lo_abre(tmp_path):
    reg = Registro()
    abiertos = []
    mod = _pystray_falso()
    bandeja = tray.BandejaDelSistema(reg.abrir, reg.salir, str(tmp_path / "x.ico"),
                                     confirmar=reg.confirmar, pystray_mod=mod,
                                     al_configurar=lambda: abiertos.append(1))
    try:
        assert bandeja.iniciar()
        icono = mod.iconos[0]
        assert [i.texto for i in icono.menu.items] == [
            tray.TEXTO_ABRIR, tray.TEXTO_IMPRESORAS, tray.TEXTO_SALIR]
        icono.item(tray.TEXTO_IMPRESORAS).accion()
        assert abiertos == [1] and reg.salidas == 0
    finally:
        bandeja.detener()


def test_salir_pide_confirmacion_y_si_no_confirma_no_sale(tmp_path):
    reg = Registro(confirma=False)
    mod = _pystray_falso()
    bandeja = tray.BandejaDelSistema(reg.abrir, reg.salir, str(tmp_path / "x.ico"),
                                     confirmar=reg.confirmar, pystray_mod=mod)
    try:
        assert bandeja.iniciar()
        mod.iconos[0].item(tray.TEXTO_SALIR).accion()
        assert reg.preguntas == 1
        assert reg.salidas == 0
    finally:
        bandeja.detener()


def test_salir_confirmado_sale(bandeja_falsa):
    bandeja, reg, mod = bandeja_falsa
    assert bandeja.iniciar()
    mod.iconos[0].item(tray.TEXTO_SALIR).accion()
    assert (reg.preguntas, reg.salidas) == (1, 1)


def test_si_no_se_puede_preguntar_no_sale(tmp_path):
    """Dejar de imprimir por un error del cuadro de diálogo sería peor."""
    reg = Registro()
    mod = _pystray_falso()

    def confirmar_roto():
        raise OSError("sin user32")

    bandeja = tray.BandejaDelSistema(reg.abrir, reg.salir, str(tmp_path / "x.ico"),
                                     confirmar=confirmar_roto, pystray_mod=mod)
    try:
        assert bandeja.iniciar()
        mod.iconos[0].item(tray.TEXTO_SALIR).accion()
        assert reg.salidas == 0
    finally:
        bandeja.detener()


def test_avisa_solo_con_el_icono_visible(bandeja_falsa):
    bandeja, reg, mod = bandeja_falsa
    assert bandeja.avisar("antes de iniciar") is False

    assert bandeja.iniciar()
    assert _esperar(lambda: bandeja.activa)
    assert bandeja.avisar(tray.AVISO_SEGUNDO_PLANO) is True
    assert mod.iconos[0].avisos == [(tray.AVISO_SEGUNDO_PLANO, tray.TITULO)]


def test_detener_saca_el_icono_y_termina_el_hilo(bandeja_falsa):
    bandeja, reg, mod = bandeja_falsa
    assert bandeja.iniciar()
    assert _esperar(lambda: bandeja.activa)

    bandeja.detener(timeout=2)
    assert bandeja.activa is False
    assert not bandeja._hilo.is_alive()


def test_sin_pystray_no_hay_bandeja_y_no_explota(tmp_path, monkeypatch):
    def import_que_falla(nombre):
        raise ImportError(f"No module named {nombre!r}")

    monkeypatch.setattr(tray.importlib, "import_module", import_que_falla)
    bandeja = tray.BandejaDelSistema(lambda: None, lambda: None, str(tmp_path / "x.ico"))
    assert bandeja.iniciar() is False
    assert bandeja.activa is False


def test_un_error_en_el_hilo_deja_la_bandeja_inactiva(tmp_path):
    mod = _pystray_falso()

    def run_roto(self, setup=None):
        raise RuntimeError("Shell_NotifyIcon falló")

    mod.Icon.run = run_roto
    bandeja = tray.BandejaDelSistema(lambda: None, lambda: None, str(tmp_path / "x.ico"),
                                     pystray_mod=mod)
    assert bandeja.iniciar() is True
    bandeja._hilo.join(2)
    assert bandeja.activa is False


def test_usa_el_icono_de_fiscalberry():
    import os
    from fiscalberry.ui import __file__ as ui_init

    ruta = os.path.join(os.path.dirname(ui_init), "assets", "fiscalberry.ico")
    bandeja = tray.BandejaDelSistema(lambda: None, lambda: None, ruta)
    imagen = bandeja._cargar_imagen()
    assert imagen.size[0] >= 16
