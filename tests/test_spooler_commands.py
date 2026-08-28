# coding=utf-8
"""
Tests de la integración ComandosHandler <-> DurablePrintSpooler para
fiscalberry#166: "Imprimir todos" / "Descartar" como comandos JSON remotos, y
del cierre ordenado del spooler (fiscalberry#165) desde ComandosHandler.

Usan un spooler falso (sin SQLite real ni impresora) para no depender de
threads/timing: lo que se prueba acá es el WIRING (que ComandosHandler llame
a los métodos correctos y devuelva el payload esperado), no la lógica interna
del spooler (eso ya lo cubre test_print_spooler.py).
"""

import pytest

from fiscalberry.common import ComandosHandler as ch


class SpoolerFalso:
    def __init__(self, pending=0, failed=0):
        self._pending = pending
        self._failed = failed
        self.requeue_calls = 0
        self.discard_calls = 0
        self.stop_calls = 0

    def requeue_failed(self):
        self.requeue_calls += 1
        n = self._failed
        self._pending += self._failed
        self._failed = 0
        return n

    def discard_all(self):
        self.discard_calls += 1
        n = self._pending + self._failed
        self._pending = 0
        self._failed = 0
        return n

    def pending_count(self):
        return self._pending

    def failed_count(self):
        return self._failed

    def stop(self):
        self.stop_calls += 1


@pytest.fixture(autouse=True)
def _reset_singleton():
    """El spooler es un singleton a nivel módulo; aislar tests entre sí."""
    ch._print_spooler = None
    yield
    ch._print_spooler = None


def test_spooler_requeue_failed_command(monkeypatch):
    fake = SpoolerFalso(pending=0, failed=3)
    monkeypatch.setattr(ch, "get_print_spooler", lambda: fake)

    handler = ch.ComandosHandler()
    rta = handler.send_command({"spoolerRequeueFailed": True})

    assert "err" not in rta
    assert rta["rta"]["requeued"] == 3
    assert rta["rta"]["pending_count"] == 3
    assert rta["rta"]["failed_count"] == 0
    assert fake.requeue_calls == 1


def test_spooler_discard_pending_command(monkeypatch):
    fake = SpoolerFalso(pending=5, failed=2)
    monkeypatch.setattr(ch, "get_print_spooler", lambda: fake)

    handler = ch.ComandosHandler()
    rta = handler.send_command({"spoolerDiscardPending": True})

    assert "err" not in rta
    assert rta["rta"]["discarded"] == 7
    assert rta["rta"]["pending_count"] == 0
    assert rta["rta"]["failed_count"] == 0
    assert fake.discard_calls == 1


def test_close_print_spooler_if_running_noop_when_never_used():
    """No debe instanciar un spooler nuevo solo para cerrarlo."""
    assert ch._print_spooler is None
    ch.close_print_spooler_if_running()
    assert ch._print_spooler is None


def test_close_print_spooler_if_running_stops_existing_instance():
    fake = SpoolerFalso()
    ch._print_spooler = fake

    ch.close_print_spooler_if_running()

    assert fake.stop_calls == 1
    assert ch._print_spooler is None
