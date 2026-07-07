# coding=utf-8
"""
Tests del enrutamiento de impresión en ComandosHandler (Fase 1).

Verifican que un ticket con `printerName` se encola en el spooler durable y
responde "aceptado" de inmediato, sin depender de una impresora real ni bloquear.
También cubren dedup por job_id, preservación de payload RAW y el flag legacy
`sync_print_commands`.

Requiere las deps de runtime (paho, escpos); si faltan, el módulo se salta.
Ejecutar con el venv del proyecto:
    venv.cli/bin/python -m pytest tests/test_comandos_handler.py -v
"""

import pytest

pytest.importorskip("paho")
pytest.importorskip("escpos")

import fiscalberry.common.ComandosHandler as CH  # noqa: E402


class FakeSpooler:
    """Spooler de prueba: registra enqueues, deduplica por job_id, no imprime."""

    def __init__(self):
        self.calls = []
        self._jobs = set()

    def enqueue(self, job_id, ticket, printer_name=None):
        self.calls.append((job_id, ticket, printer_name))
        is_new = job_id not in self._jobs
        self._jobs.add(job_id)
        return is_new

    def pending_count(self):
        return len(self._jobs)

    def failed_count(self):
        return 0


@pytest.fixture
def fake_spooler(monkeypatch):
    fake = FakeSpooler()
    monkeypatch.setattr(CH, "_print_spooler", fake)
    monkeypatch.setattr(CH, "_is_sync_print_mode", lambda: False)
    return fake


def test_ticket_with_printer_is_enqueued_and_accepted(fake_spooler):
    handler = CH.ComandosHandler()
    resp = handler.send_command({"printerName": "cocina", "printTexto": {"texto": "hola"}})

    r = resp["rta"]
    assert r["accepted"] is True
    assert r["queued"] is True
    assert r["duplicate"] is False
    assert r["job_id"]
    assert r["pending_count"] == 1
    assert r["failed_count"] == 0

    # Se encoló una vez, conservando printerName en el ticket persistido.
    assert len(fake_spooler.calls) == 1
    job_id, ticket, printer_name = fake_spooler.calls[0]
    assert printer_name == "cocina"
    assert ticket.get("printerName") == "cocina"


def test_duplicate_job_id_is_marked_duplicate(fake_spooler):
    handler = CH.ComandosHandler()
    ticket = {"printerName": "cocina", "jobId": "abc-123", "printTexto": {"texto": "x"}}

    resp1 = handler.send_command(dict(ticket))
    resp2 = handler.send_command(dict(ticket))

    assert resp1["rta"]["duplicate"] is False
    assert resp2["rta"]["duplicate"] is True
    # Mismo job_id explícito en ambos.
    assert fake_spooler.calls[0][0] == "abc-123"
    assert fake_spooler.calls[1][0] == "abc-123"


def test_printraw_payload_reaches_spooler_intact(fake_spooler):
    handler = CH.ComandosHandler()
    raw = {
        "printerName": "cocina",
        "printRaw": {"data": "H4sIAAAAAAAA/wtJLS7hAgAAAP//", "encoding": "gzip+base64"},
    }
    handler.send_command(dict(raw))

    _, ticket, _ = fake_spooler.calls[0]
    assert ticket["printRaw"] == raw["printRaw"]


def test_durable_path_does_not_require_real_printer(fake_spooler):
    """Impresora inexistente: igual se acepta durablemente sin lanzar ni bloquear."""
    handler = CH.ComandosHandler()
    resp = handler.send_command({"printerName": "no_existe", "printTexto": {"texto": "z"}})
    assert resp["rta"]["accepted"] is True
    assert "err" not in resp


def test_sync_print_mode_flag(monkeypatch):
    monkeypatch.setattr(CH.configberry, "get", lambda s, k, fallback=None: "false")
    assert CH._is_sync_print_mode() is False

    monkeypatch.setattr(CH.configberry, "get", lambda s, k, fallback=None: "true")
    assert CH._is_sync_print_mode() is True


def test_compute_job_id_stable_and_uses_jobid():
    # jobId explícito manda.
    assert CH._compute_job_id({"jobId": "fixed", "a": 1}) == "fixed"
    # Sin jobId: sha1 estable e independiente del orden de claves.
    a = CH._compute_job_id({"printerName": "p", "a": 1, "b": 2})
    b = CH._compute_job_id({"b": 2, "printerName": "p", "a": 1})
    assert a == b and len(a) == 40
