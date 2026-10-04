# coding=utf-8
"""
Tests del spooler durable (DurablePrintSpooler).

Cubren el contrato central de "nunca perder impresiones":
  - dedup por job_id (INSERT OR IGNORE)
  - trabajo OK se borra
  - trabajo que falla reintenta y termina en 'failed' (dead-letter)
  - recuperación al reiniciar (_recover_on_start re-encola 'failed')
  - el payload (incluido RAW) se serializa/deserializa sin mutar
  - durabilidad ante power-cycle (issue #165): PRAGMA synchronous=FULL y
    visibilidad de lo persistido sin depender de un cierre ordenado
  - discard_all() / requeue_failed() sin romper la dedup (issue #166)

El spooler corre un worker en un thread daemon. Los tests usan un print_fn
controlado y hacen polling con timeout corto para ser deterministas sin sleeps
frágiles.
"""

import sqlite3
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


# ---------------------------------------------------------------------------
# Regresión #165: durabilidad ante power-cycle.
#
# Un power-cycle real (o un `kill -9`) no se puede reproducir de forma
# determinista en un test de proceso único: eso requeriría interceptar fsync()
# a nivel de SO. Lo que SÍ se puede verificar sin ambigüedad es la causa raíz
# encontrada en la issue: la conexión abría en WAL sin fijar `synchronous`, y
# el default de SQLite en WAL (NORMAL) no hace fsync en cada commit. Estos
# tests fijan esa regresión a nivel de PRAGMA, y además documentan que lo
# persistido es visible para OTRA conexión sin pasar por un stop() prolijo
# (que es exactamente lo que un corte de luz NO permite hacer).
# ---------------------------------------------------------------------------

def test_synchronous_pragma_is_full(db_path):
    """La conexión del spooler debe quedar en synchronous=FULL (no el NORMAL
    por default de WAL). Es el fix directo de la hipótesis de la #165: con
    NORMAL el commit no fsyncea el WAL y un corte de energía puede perder
    todo lo escrito desde el último checkpoint."""
    sp = DurablePrintSpooler(lambda t: None, db_path=db_path, idle_wait=0.1)
    try:
        mode = sp._conn.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = sp._conn.execute("PRAGMA synchronous").fetchone()[0]
        assert str(mode).lower() == "wal"
        # SQLite: OFF=0, NORMAL=1, FULL=2, EXTRA=3. Debe ser FULL o superior,
        # nunca NORMAL (el default sin este fix) ni OFF.
        assert synchronous >= 2, (
            f"synchronous={synchronous} (se esperaba FULL=2): con NORMAL/OFF "
            "el commit no fsyncea y un power-cycle puede perder jobs (#165)")
    finally:
        sp.stop()


def test_pending_job_visible_to_other_connection_without_clean_stop(db_path):
    """Un job 'pending' debe ser visible desde OTRA conexión al mismo .db sin
    que el proceso original haya pasado por un stop() prolijo (que hace
    checkpoint + close). Reproduce la consulta exacta de la issue #165
    (`SELECT status, COUNT(*) FROM jobs GROUP BY status`) para confirmar que
    lo persistido no depende de un cierre ordenado."""

    def offline_print_fn(ticket):
        raise RuntimeError("impresora offline")

    sp = DurablePrintSpooler(
        offline_print_fn, db_path=db_path, max_attempts=1000, base_delay=0.02,
        max_delay=0.05, idle_wait=0.05,
    )
    try:
        sp.enqueue("job-a", {"a": 1}, "printerA")
        sp.enqueue("job-b", {"b": 2}, "printerA")
        assert _wait_until(lambda: sp.pending_count() == 2, timeout=5.0)

        # Conexión de solo lectura independiente: NO pasa por sp.stop().
        raw = sqlite3.connect(db_path)
        try:
            counts = dict(raw.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall())
        finally:
            raw.close()
        assert counts.get("pending") == 2
        assert counts.get("failed") is None
    finally:
        sp.stop()


def test_stop_closes_connection_cleanly(db_path):
    """stop() debe cerrar la conexión y dejar la cola consistente para que un
    reinicio inmediato (nueva instancia sobre el mismo archivo) no choque con
    un lock ni pierda datos."""

    def offline_print_fn(ticket):
        raise RuntimeError("impresora offline")

    sp = DurablePrintSpooler(
        offline_print_fn, db_path=db_path, max_attempts=1000, base_delay=0.02,
        max_delay=0.05, idle_wait=0.05,
    )
    assert sp.enqueue("job-x", {"x": 1}, "printerA") is True
    assert _wait_until(lambda: sp.pending_count() == 1, timeout=5.0)
    sp.stop()

    # La conexión interna quedó cerrada: ejecutar sobre ella debe fallar.
    with pytest.raises(sqlite3.ProgrammingError):
        sp._conn.execute("SELECT 1")

    # Una instancia nueva sobre el mismo archivo debe abrir sin bloquearse
    # (sin "database is locked") y ver el job que quedó sin imprimir.
    sp2 = DurablePrintSpooler(offline_print_fn, db_path=db_path, idle_wait=5.0)
    try:
        assert sp2.pending_count() == 1
    finally:
        sp2.stop()


# ---------------------------------------------------------------------------
# Regresión #166: discard_all() / requeue_failed() sin romper la dedup.
# ---------------------------------------------------------------------------

def test_discard_all_clears_pending_and_failed(db_path):
    """discard_all() vacía tanto 'pending' como 'failed' y devuelve cuántos."""

    def offline_print_fn(ticket):
        raise RuntimeError("impresora offline")

    sp = DurablePrintSpooler(
        offline_print_fn, db_path=db_path, max_attempts=1, base_delay=0.02,
        max_delay=0.05, idle_wait=0.05,
    )
    try:
        sp.enqueue("job-fail", {"x": 1}, "printerA")
        assert _wait_until(lambda: sp.failed_count() == 1, timeout=5.0)

        n = sp.discard_all()
        assert n == 1
        assert sp.pending_count() == 0
        assert sp.failed_count() == 0
    finally:
        sp.stop()


def test_discard_all_then_same_job_id_is_accepted_again(db_path):
    """La dedup es por fila viva: tras descartar, el mismo job_id ya NO está
    en la tabla, así que un reenvío (ej. reintento del servidor) se vuelve a
    aceptar como job nuevo. Es el comportamiento esperado de "descartar": no
    debe quedar un tombstone que bloquee reintentos futuros legítimos."""
    block = threading.Event()

    def blocking_fn(ticket):
        block.wait(timeout=3.0)

    sp = DurablePrintSpooler(blocking_fn, db_path=db_path, base_delay=0.05, idle_wait=0.1)
    try:
        assert sp.enqueue("job-1", {"a": 1}, "printerA") is True
        assert sp.enqueue("job-1", {"a": 1}, "printerA") is False  # dedup normal

        n = sp.discard_all()
        assert n == 1

        assert sp.enqueue("job-1", {"a": 1}, "printerA") is True
    finally:
        block.set()
        sp.stop()


def test_requeue_failed_moves_failed_back_to_pending_and_wakes_worker(db_path):
    """requeue_failed() (issue #166, 'imprimir todos') re-encola los 'failed'
    y despierta al worker: no hace falta esperar el idle_wait para que se
    reintenten."""
    attempts = {"n": 0}

    def flaky_fn(ticket):
        attempts["n"] += 1
        if attempts["n"] <= 1:
            raise RuntimeError("impresora offline")
        # segundo intento (tras requeue_failed) sale bien

    sp = DurablePrintSpooler(
        flaky_fn, db_path=db_path, max_attempts=1, base_delay=0.02,
        max_delay=0.05, idle_wait=5.0,  # idle_wait largo: sin wake, tardaría
    )
    try:
        sp.enqueue("job-flaky", {"x": 1}, "printerA")
        assert _wait_until(lambda: sp.failed_count() == 1, timeout=5.0)

        n = sp.requeue_failed()
        assert n == 1

        assert _wait_until(lambda: sp.pending_count() == 0 and sp.failed_count() == 0,
                            timeout=2.0)
        assert attempts["n"] == 2
    finally:
        sp.stop()
