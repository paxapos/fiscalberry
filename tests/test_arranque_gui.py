# coding=utf-8
"""
El arranque de la GUI con otra instancia ya corriendo.

Dos cosas que este archivo fija:

- Abrir Fiscalberry con otra instancia viva no levanta un segundo proceso: le
  pide a la existente que muestre su ventana y termina. El arranque con la
  sesión (`--minimized`) ni siquiera eso: si ya hay uno, no hace falta mostrar
  nada.
- El candado se toma ANTES de contar el arranque de una actualización. Si la
  instancia rechazada pasara por on_process_start(), tres aperturas desde el
  acceso directo revertirían una versión recién instalada que andaba bien.
"""

import pytest

from fiscalberry.common import single_instance
from fiscalberry.common.updater import service as updater_service
from fiscalberry.desktop import main as gui_main


class Llamadas:
    def __init__(self):
        self.orden = []


@pytest.fixture
def arranque(monkeypatch):
    """main() sin Kivy, sin logs a archivo y con la instancia única simulada."""
    reg = Llamadas()
    monkeypatch.setattr(gui_main, "handle_early_modes", lambda: False)
    monkeypatch.setattr(gui_main, "setup_file_logging", lambda role: None)
    monkeypatch.setattr(gui_main, "_registrar_crashes", lambda: None)
    monkeypatch.setattr(gui_main, "_app", None)
    monkeypatch.setattr(gui_main, "_mostrar_pendiente", False)
    monkeypatch.setattr(updater_service, "on_process_start",
                        lambda: reg.orden.append("on_process_start"))
    monkeypatch.setattr(single_instance, "start_activation_listener",
                        lambda cb: reg.orden.append("escucha"))
    monkeypatch.setattr(single_instance, "notify_running_instance",
                        lambda timeout=3.0: reg.orden.append("aviso") or True)
    return reg


def _con_candado(monkeypatch, reg, resultado):
    def tomar():
        reg.orden.append("candado")
        return resultado
    monkeypatch.setattr(single_instance, "acquire_single_instance_lock", tomar)


def test_con_otra_instancia_viva_le_pide_mostrarse_y_no_cuenta_el_arranque(
        arranque, monkeypatch):
    _con_candado(monkeypatch, arranque, False)
    monkeypatch.setattr(gui_main.sys, "argv", ["fiscalberry-gui.exe"])

    gui_main.main()

    assert arranque.orden == ["candado", "aviso"]


def test_el_arranque_con_la_sesion_no_muestra_la_otra_ventana(arranque, monkeypatch):
    _con_candado(monkeypatch, arranque, False)
    monkeypatch.setattr(gui_main.sys, "argv", ["fiscalberry-gui.exe", "--minimized"])

    gui_main.main()

    assert arranque.orden == ["candado"]


def test_la_instancia_unica_escucha_antes_de_contar_el_arranque(arranque, monkeypatch):
    _con_candado(monkeypatch, arranque, True)
    monkeypatch.setattr(gui_main.sys, "argv", ["fiscalberry-gui.exe"])

    class AppFalsa:
        start_minimized = None
        mostradas = 0

        def mostrar_ventana(self):
            AppFalsa.mostradas += 1

        def run(self):
            arranque.orden.append("run")

    import types
    import sys
    modulo = types.ModuleType("fiscalberry.ui.fiscalberry_app")
    modulo.FiscalberryApp = AppFalsa
    monkeypatch.setitem(sys.modules, "fiscalberry.ui.fiscalberry_app", modulo)

    gui_main.main()

    assert arranque.orden == ["candado", "escucha", "on_process_start", "run"]
    assert AppFalsa.mostradas == 0


def test_un_pedido_que_llega_antes_de_que_exista_la_app_no_se_pierde(
        arranque, monkeypatch):
    """Se abrió el acceso directo mientras la instancia del arranque cargaba."""
    _con_candado(monkeypatch, arranque, True)
    monkeypatch.setattr(gui_main.sys, "argv", ["fiscalberry-gui.exe", "--minimized"])
    monkeypatch.setattr(gui_main, "_arrancar_sin_ventana", lambda: None)

    class AppFalsa:
        start_minimized = None
        mostradas = 0

        def mostrar_ventana(self):
            AppFalsa.mostradas += 1

        def run(self):
            pass

    import types
    import sys
    modulo = types.ModuleType("fiscalberry.ui.fiscalberry_app")
    modulo.FiscalberryApp = AppFalsa
    monkeypatch.setitem(sys.modules, "fiscalberry.ui.fiscalberry_app", modulo)

    # El hilo de activación atiende el pedido antes de que exista la app.
    gui_main._pedido_de_mostrar_ventana()
    gui_main.main()

    assert AppFalsa.mostradas == 1


def test_minimized_se_consume_antes_de_que_lo_vea_kivy():
    argv = ["fiscalberry-gui.exe", "--minimized"]
    assert gui_main.consume_start_minimized(argv) is True
    assert argv == ["fiscalberry-gui.exe"]
