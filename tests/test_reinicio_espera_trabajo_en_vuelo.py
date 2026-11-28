# coding=utf-8
"""
`restart`, `upgrade` y `reboot` no reimprimen el trabajo que estaba imprimiéndose (#224).

Los tres terminan en `ServiceController._stop_services_only()`: `restart` y el
`upgrade` que reinicia desde su propio hilo, `reboot` por el SIGTERM que manda
el sistema al apagar. Ahí, `_stop_event` hace que el bucle principal termine y,
en la CLI, con él el proceso (los demás hilos son daemon). Si eso pasa con un
trabajo a medio imprimir, el trabajo sigue 'pending' en la base y se imprime
otra vez al volver.

Lo que se fija: el servicio corta recién cuando el trabajo en vuelo terminó (o
venció el tope, con un aviso), y los que no arrancaron quedan 'pending'.
"""

import logging
import sqlite3
import threading

import pytest

pytest.importorskip("paho")
pytest.importorskip("escpos")

import fiscalberry.common.ComandosHandler as CH  # noqa: E402
from fiscalberry.common import service_controller as sc_mod  # noqa: E402
from fiscalberry.common.print_spooler import DurablePrintSpooler  # noqa: E402


class SioFalso:
    def stop(self):
        pass


def _trabajos(db_path):
    con = sqlite3.connect(db_path)
    try:
        return sorted(con.execute("SELECT job_id, status FROM jobs").fetchall())
    finally:
        con.close()


@pytest.fixture
def servicio(tmp_path, monkeypatch):
    """Servicio con el spooler real y un trabajo en vuelo hasta que se suelte."""
    en_vuelo, soltar = threading.Event(), threading.Event()

    def print_fn(ticket):
        en_vuelo.set()
        soltar.wait(timeout=5.0)

    db_path = str(tmp_path / "spool.db")
    sp = DurablePrintSpooler(print_fn, db_path=db_path, idle_wait=0.05)
    monkeypatch.setattr(CH, "_print_spooler", sp)
    # Si alguien creara otro spooler, que no sea sobre la base real del equipo.
    monkeypatch.setattr("fiscalberry.common.print_spooler.default_db_path",
                        lambda: str(tmp_path / "otro_spooler.db"))
    sp.enqueue("en-vuelo", {"n": 1}, "cocina")
    sp.enqueue("sin-arrancar", {"n": 2}, "cocina")
    assert en_vuelo.wait(timeout=2.0)

    ctrl = object.__new__(sc_mod.ServiceController)   # sin __init__: no toca el config
    ctrl._stop_event = threading.Event()
    ctrl.updater = None
    ctrl.sio = SioFalso()
    ctrl.socketio_thread = None
    ctrl.discover_thread = None
    monkeypatch.setattr(sc_mod, "clear_status", lambda: None)

    ctrl.soltar, ctrl.db_path = soltar, db_path
    yield ctrl
    soltar.set()


def test_el_servicio_corta_recien_cuando_termina_el_trabajo_en_vuelo(servicio):
    hilo = threading.Thread(target=servicio._stop_services_only, daemon=True)
    hilo.start()

    # Con el trabajo imprimiéndose, el bucle principal (y el proceso) sigue vivo.
    assert not servicio._stop_event.wait(timeout=0.3)

    servicio.soltar.set()
    hilo.join(timeout=5.0)

    assert servicio._stop_event.is_set()
    # El que estaba en vuelo quedó impreso; el que no arrancó sigue en la base.
    assert _trabajos(servicio.db_path) == [("sin-arrancar", "pending")]


def test_si_el_trabajo_no_termina_antes_del_tope_corta_igual_y_avisa(servicio, monkeypatch,
                                                                     caplog):
    monkeypatch.setattr(CH, "ESPERA_TRABAJO_EN_VUELO", 0.2)

    with caplog.at_level(logging.WARNING):
        servicio._stop_services_only()

    assert servicio._stop_event.is_set()
    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("no terminó" in m for m in avisos)
    assert _trabajos(servicio.db_path) == [("en-vuelo", "pending"), ("sin-arrancar", "pending")]


def test_un_trabajo_que_llega_durante_la_espera_queda_en_la_cola(servicio):
    """Mientras se espera al trabajo en vuelo, lo que llega por MQTT se persiste
    en el mismo spooler (no en uno nuevo que se pondría a imprimir)."""
    hilo = threading.Thread(target=servicio._stop_services_only, daemon=True)
    hilo.start()
    assert not servicio._stop_event.wait(timeout=0.2)

    assert CH.get_print_spooler().enqueue("llego-tarde", {"n": 3}, "cocina") is True

    servicio.soltar.set()
    hilo.join(timeout=5.0)
    assert _trabajos(servicio.db_path) == [("llego-tarde", "pending"), ("sin-arrancar", "pending")]
