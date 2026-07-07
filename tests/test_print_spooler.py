# coding=utf-8
"""
Tests del spooler durable (DurablePrintSpooler).

Cubren el contrato central de "nunca perder impresiones":
  - dedup por job_id (INSERT OR IGNORE)
  - trabajo OK se borra
  - trabajo que falla reintenta y termina en 'failed' (dead-letter)
  - recuperación al reiniciar (_recover_on_start re-encola 'failed')
  - el payload (incluido RAW) se serializa/deserializa sin mutar

El spooler corre un worker en un thread daemon. Los tests usan un print_fn
controlado y hacen polling con timeout corto para ser deterministas sin sleeps
frágiles.
"""

import threading
import time

import pytest

from fiscalberry.common.print_spooler import DurablePrintSpooler


def _wait_until(predicate, timeout=5.0, interval=0.02):
    """Espera hasta que predicate() sea verdadero o se agote el timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "spool_test.db")


def test_enqueue_new_returns_true_duplicate_returns_false(db_path):
    """enqueue del mismo job_id inserta una sola vez (dedup QoS1)."""
    printed = []
    block = threading.Event()

    def print_fn(ticket):
        # Bloquea para que el worker no drene la cola durante las aserciones.
        block.wait(timeout=2.0)
        printed.append(ticket)

    sp = DurablePrintSpooler(print_fn, db_path=db_path, base_delay=0.05, idle_wait=0.1)
    try:
        assert sp.enqueue("job-1", {"a": 1}, "printerA") is True
        assert sp.enqueue("job-1", {"a": 1}, "printerA") is False
    finally:
        block.set()
        sp.stop()


def test_successful_job_is_deleted(db_path):
    """Un trabajo impreso OK se borra de la cola (pending_count -> 0)."""
    printed = []

    def print_fn(ticket):
        printed.append(ticket)

    sp = DurablePrintSpooler(print_fn, db_path=db_path, base_delay=0.05, idle_wait=0.1)
    try:
        sp.enqueue("job-ok", {"hello": "world"}, "printerA")
        assert _wait_until(lambda: sp.pending_count() == 0)
        assert printed == [{"hello": "world"}]
        assert sp.failed_count() == 0
    finally:
        sp.stop()


def test_failing_job_retries_then_dead_letters(db_path):
    """Un trabajo que siempre falla reintenta y termina en 'failed'."""
    attempts = {"n": 0}

    def print_fn(ticket):
        attempts["n"] += 1
        raise RuntimeError("impresora offline")

    sp = DurablePrintSpooler(
        print_fn, db_path=db_path, max_attempts=2, base_delay=0.02,
        max_delay=0.05, idle_wait=0.05,
    )
    try:
        sp.enqueue("job-fail", {"x": 1}, "printerA")
        assert _wait_until(lambda: sp.failed_count() == 1, timeout=5.0)
        assert attempts["n"] >= 2
        assert sp.pending_count() == 0
    finally:
        sp.stop()


def test_recover_on_start_requeues_failed_jobs(db_path):
    """Al reiniciar, los 'failed' se re-encolan a 'pending' (recuperación)."""
    # 1) Primer spooler: el print_fn siempre falla -> el job cae a 'failed'.
    def failing_fn(ticket):
        raise RuntimeError("boom")

    sp1 = DurablePrintSpooler(
        failing_fn, db_path=db_path, max_attempts=1, base_delay=0.02,
        max_delay=0.05, idle_wait=0.05,
    )
    sp1.enqueue("job-recover", {"y": 2}, "printerA")
    assert _wait_until(lambda: sp1.failed_count() == 1, timeout=5.0)
    sp1.stop()

    # 2) Segundo spooler sobre la misma DB: print_fn bloquea para poder observar
    #    el estado recuperado antes de que el worker lo drene.
    release = threading.Event()

    def blocking_fn(ticket):
        release.wait(timeout=3.0)

    sp2 = DurablePrintSpooler(blocking_fn, db_path=db_path, base_delay=0.05, idle_wait=0.1)
    try:
        # _recover_on_start corre en __init__ antes de arrancar el worker.
        assert sp2.failed_count() == 0
        assert sp2.pending_count() == 1
    finally:
        release.set()
        sp2.stop()


def test_payload_roundtrip_preserves_raw_fields(db_path):
    """El ticket (incluido payload RAW) llega intacto a print_fn."""
    captured = []
    done = threading.Event()

    def print_fn(ticket):
        captured.append(ticket)
        done.set()

    raw_ticket = {
        "printerName": "printerA",
        "printRaw": {
            "data": "H4sIAAAAAAAA/wtJLS7hAgAAAP//",
            "encoding": "gzip+base64",
        },
        "unicode": "áéí ñ €",
    }

    sp = DurablePrintSpooler(print_fn, db_path=db_path, base_delay=0.05, idle_wait=0.1)
    try:
        sp.enqueue("job-raw", raw_ticket, "printerA")
        assert done.wait(timeout=5.0)
        assert captured[0] == raw_ticket
    finally:
        sp.stop()
