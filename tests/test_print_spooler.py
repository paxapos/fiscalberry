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


def test_synchronous_pragma_is_full(db_path):
    """fiscalberry#165: en WAL, el default synchronous=NORMAL puede perder
    transacciones confirmadas ante un corte de luz (no hace fsync en cada
    commit). El spooler debe forzar FULL explícitamente (valor pragma 2)."""
    sp = DurablePrintSpooler(lambda ticket: None, db_path=db_path, idle_wait=0.1)
    try:
        value = sp._conn.execute("PRAGMA synchronous").fetchone()[0]
        assert value == 2  # 0=OFF, 1=NORMAL, 2=FULL, 3=EXTRA
    finally:
        sp.stop()


def test_pending_jobs_survive_power_cycle_simulation(db_path):
    """fiscalberry#165: reproduce el escenario reportado.

    Con la impresora "caída" (print_fn siempre falla) quedan jobs 'pending'
    reintentando con backoff -- nunca llegan a 'failed' porque max_attempts es
    alto. Se simula un power-cycle SIN pasar por stop() (abrir una conexión
    nueva directamente sobre el mismo archivo, como si el proceso hubiera
    muerto de golpe): los jobs 'pending' deben seguir estando ahí y
    _recover_on_start() debe dejarlos listos para reintentar de inmediato.
    """
    def siempre_falla(ticket):
        raise RuntimeError("impresora offline")

    sp1 = DurablePrintSpooler(
        siempre_falla, db_path=db_path, max_attempts=1000,
        base_delay=0.02, max_delay=0.05, idle_wait=0.05,
    )
    for i in range(10):
        sp1.enqueue(f"job-{i}", {"n": i}, "printerA")
    assert _wait_until(lambda: sp1.pending_count() == 10, timeout=5.0)
    assert sp1.failed_count() == 0

    # "Apagado": se corta el loop del worker directamente (sin pasar por el
    # cierre ordenado de stop(): sin checkpoint, sin close() de la conexión) para
    # simular el proceso muriendo de golpe -- justo el escenario que #165
    # reporta. Es necesario frenar el thread daemon explícitamente: al ser un
    # bound method de self, sigue vivo (y seguiría escribiendo) aunque se haga
    # `del sp1`, lo que ensuciaría la comparación contra sp2 más abajo.
    sp1._stop.set()
    sp1._wake.set()
    sp1._worker.join(timeout=2.0)
    assert not sp1._worker.is_alive()

    # "Encendido": nueva instancia sobre el mismo archivo.
    def print_fn(ticket):
        pass

    sp2 = DurablePrintSpooler(print_fn, db_path=db_path, base_delay=0.05, idle_wait=0.1)
    try:
        # Los 10 jobs deben seguir en la base y quedar listos para reintentar YA
        # (next_attempt_at=0), no perdidos ni demorados por el backoff previo.
        assert sp2.pending_count() == 10
        assert sp2.failed_count() == 0
        assert _wait_until(lambda: sp2.pending_count() == 0, timeout=5.0)
    finally:
        sp2.stop()


def test_requeue_failed_moves_dead_letters_back_to_pending(db_path):
    """fiscalberry#166: requeue_failed() (botón "Imprimir todos") existía pero
    nadie la llamaba. Verifica el contrato que ahora expone ComandosHandler."""
    calls = {"n": 0}
    block_retry = threading.Event()

    def print_fn(ticket):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        # Segundo intento (tras el requeue): bloquea para poder inspeccionar el
        # estado 'pending' antes de que el worker lo vuelva a procesar.
        block_retry.wait(timeout=3.0)

    sp = DurablePrintSpooler(
        print_fn, db_path=db_path, max_attempts=1, base_delay=0.02,
        max_delay=0.05, idle_wait=0.05,
    )
    try:
        sp.enqueue("job-dead", {"z": 1}, "printerA")
        assert _wait_until(lambda: sp.failed_count() == 1, timeout=5.0)

        n = sp.requeue_failed()
        assert n == 1
        assert _wait_until(lambda: calls["n"] == 2, timeout=5.0)  # worker ya reclamó el job
        assert sp.failed_count() == 0
        assert sp.pending_count() == 1
    finally:
        block_retry.set()
        sp.stop()


def test_discard_all_purges_pending_and_failed(db_path):
    """fiscalberry#166: botón "Descartar" -- vacía la cola sin imprimir."""
    block = threading.Event()

    def print_fn(ticket):
        block.wait(timeout=3.0)

    sp = DurablePrintSpooler(print_fn, db_path=db_path, base_delay=0.05, idle_wait=0.1)
    try:
        sp.enqueue("job-a", {"a": 1}, "printerA")  # se queda bloqueado imprimiendo
        sp.enqueue("job-b", {"b": 1}, "printerA")  # se queda en 'pending'
        assert _wait_until(lambda: sp.pending_count() == 1, timeout=5.0)

        n = sp.discard_all()
        assert n == 1
        assert sp.pending_count() == 0
        assert sp.failed_count() == 0
    finally:
        block.set()
        sp.stop()


def test_stop_closes_connection(db_path):
    """fiscalberry#165 propuesta 3: stop() debe cerrar la conexión, no solo
    marcar el flag (antes el proceso podía morir con os._exit() sin haber
    cerrado nunca la conexión SQLite)."""
    sp = DurablePrintSpooler(lambda ticket: None, db_path=db_path, idle_wait=0.1)
    sp.stop()
    with pytest.raises(Exception):
        sp._conn.execute("SELECT 1")


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
