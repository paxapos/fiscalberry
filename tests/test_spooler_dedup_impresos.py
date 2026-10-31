"""
Dedup después de imprimir y un solo job id para MQTT y Socket.IO
(paxapos/fiscalberry#216, épica paxapos/paxapos#1723).
"""

import json
import sqlite3
import time

import pytest

from fiscalberry.common.job_id import compute_job_id
from fiscalberry.common.print_spooler import DurablePrintSpooler


def _wait_until(predicate, timeout=5.0, interval=0.02):
    fin = time.time() + timeout
    while time.time() < fin:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def spooler(tmp_path):
    impresos = []
    sp = DurablePrintSpooler(lambda t: impresos.append(t), db_path=str(tmp_path / "spool.db"),
                             base_delay=0.05, idle_wait=0.05)
    sp.impresos = impresos
    yield sp
    sp.stop()


def test_reentrega_del_mismo_jobid_despues_de_impreso_no_imprime(spooler):
    ticket = {"printerName": "Caja", "jobId": "comanda-5-c0-ab12cd34", "printRaw": {"data": "x"}}
    assert spooler.enqueue("comanda-5-c0-ab12cd34", ticket, "Caja") is True
    assert _wait_until(lambda: len(spooler.impresos) == 1)

    assert spooler.enqueue("comanda-5-c0-ab12cd34", ticket, "Caja") is False
    time.sleep(0.2)
    assert len(spooler.impresos) == 1


def test_sin_jobid_un_ticket_igual_ya_impreso_se_vuelve_a_imprimir(spooler):
    # sin jobId el id es el hash del contenido: dos tickets iguales pueden ser una reimpresión legítima
    ticket = {"printerName": "Caja", "printTexto": {"texto": "prueba"}}
    job_id = compute_job_id(ticket)
    assert spooler.enqueue(job_id, ticket, "Caja") is True
    assert _wait_until(lambda: len(spooler.impresos) == 1)
    assert spooler.enqueue(job_id, ticket, "Caja") is True
    assert _wait_until(lambda: len(spooler.impresos) == 2)


def test_pasada_la_retencion_el_jobid_vuelve_a_imprimirse(spooler, tmp_path):
    ticket = {"printerName": "Caja", "jobId": "remito-1-c0-11111111"}
    spooler.enqueue("remito-1-c0-11111111", ticket, "Caja")
    assert _wait_until(lambda: len(spooler.impresos) == 1)

    viejo = time.time() - DurablePrintSpooler.PRINTED_RETENTION_SECONDS - 60
    with spooler._lock:
        spooler._conn.execute("UPDATE printed_jobs SET printed_at=?", (viejo,))
        spooler._conn.commit()

    assert spooler.enqueue("remito-1-c0-11111111", ticket, "Caja") is True
    assert _wait_until(lambda: len(spooler.impresos) == 2)


def test_la_limpieza_borra_solo_lo_vencido(spooler):
    with spooler._lock:
        spooler._conn.execute("INSERT INTO printed_jobs VALUES ('viejo', ?)", (time.time() - 10 ** 6,))
        spooler._conn.execute("INSERT INTO printed_jobs VALUES ('nuevo', ?)", (time.time(),))
        spooler._conn.commit()
    assert spooler._maybe_purge_printed(force=True) == 1
    with spooler._lock:
        quedan = [r[0] for r in spooler._conn.execute("SELECT job_id FROM printed_jobs")]
    assert quedan == ["nuevo"]


def test_el_spooler_abre_una_base_creada_por_la_version_anterior(tmp_path):
    db = str(tmp_path / "vieja.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY, printer_name TEXT, payload TEXT NOT NULL, "
                 "status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, "
                 "next_attempt_at REAL NOT NULL DEFAULT 0, last_error TEXT, created_at REAL NOT NULL, "
                 "updated_at REAL NOT NULL)")
    conn.execute("INSERT INTO jobs VALUES ('j1', 'Caja', ?, 'pending', 0, 0, NULL, 0, 0)",
                 (json.dumps({"printerName": "Caja", "jobId": "j1"}),))
    conn.commit()
    conn.close()

    impresos = []
    sp = DurablePrintSpooler(lambda t: impresos.append(t), db_path=db, base_delay=0.05, idle_wait=0.05)
    try:
        assert _wait_until(lambda: len(impresos) == 1)
        assert sp.enqueue("j1", {"printerName": "Caja", "jobId": "j1"}, "Caja") is False
    finally:
        sp.stop()


def test_mismo_ticket_por_mqtt_y_por_socketio_tiene_el_mismo_id():
    from fiscalberry.common.ComandosHandler import _compute_job_id

    ticket = {"printerName": "Cocina", "printComanda": {"comanda": {"id": 3, "platos": [{"nombre": "Ñoquis", "cant": 1}]}}}
    # MQTT recibe el body en el orden que lo serializó el servidor; SIO lo arma en otro orden
    por_mqtt = json.loads(json.dumps(ticket))
    por_sio = {"printComanda": ticket["printComanda"], "printerName": "Cocina"}
    assert compute_job_id(por_mqtt) == _compute_job_id(por_sio)


def test_el_jobid_explicito_manda():
    assert compute_job_id({"jobId": "arqueo-9-c0-deadbeef", "printerName": "x"}) == "arqueo-9-c0-deadbeef"
    assert compute_job_id({"jobId": 77}) == "77"
