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
        self.requeue_failed_calls = 0
        self.discard_all_calls = 0
        self._failed = set()

    def enqueue(self, job_id, ticket, printer_name=None):
        self.calls.append((job_id, ticket, printer_name))
        is_new = job_id not in self._jobs
        self._jobs.add(job_id)
        return is_new

    def pending_count(self):
        return len(self._jobs)

    def failed_count(self):
        return len(self._failed)

    def requeue_failed(self):
        """Simula mover 'failed' -> 'pending' (issue #166, 'imprimir todos')."""
        self.requeue_failed_calls += 1
        n = len(self._failed)
        self._jobs |= self._failed
        self._failed.clear()
        return n

    def discard_all(self):
        """Simula vaciar 'pending' + 'failed' (issue #166, 'descartar')."""
        self.discard_all_calls += 1
        n = len(self._jobs) + len(self._failed)
        self._jobs.clear()
        self._failed.clear()
        return n


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


def test_jobid_is_stripped_before_translating(monkeypatch):
    """El jobId (metadata de dedup del spooler) no debe llegar a EscPComandos
    como si fuera una accion: generaba 'Function not found' en la respuesta."""

    class FakeConfigberry:
        def get_config_for_printer(self, name):
            return {"driver": "Dummy"}

    monkeypatch.setattr(CH, "configberry", FakeConfigberry())

    ticket = {"printerName": "cocina", "jobId": "job-1", "printTexto": {"texto": "hola"}}
    resp = CH.runTraductor(ticket, None)

    actions = [item.get("action") for item in resp["result"]]
    assert "printTexto" in actions
    assert "jobId" not in actions
    assert not any(item.get("rta") == "Function not found" for item in resp["result"])


def test_setup_id_no_se_envia_al_constructor_del_driver(monkeypatch):
    real_dummy = CH.printer.Dummy

    def dummy_sin_metadata(**kwargs):
        assert "_setup_id" not in kwargs
        return real_dummy(**kwargs)

    class FakeConfigberry:
        def get_config_for_printer(self, name):
            return {"driver": "Dummy", "_setup_id": "windows:Cocina"}

    monkeypatch.setattr(CH, "configberry", FakeConfigberry())
    monkeypatch.setattr(CH.printer, "Dummy", dummy_sin_metadata)

    response = CH.runTraductor(
        {"printerName": "Cocina", "printTexto": {"texto": "prueba"}},
        None,
    )

    assert response["message"] == "Impresión exitosa"


def test_serial_recibe_baudrate_y_timeout_como_numeros_y_sin_metadatos(monkeypatch):
    """Lo que guarda el asistente para un USB que aparece como COM (#171)."""
    recibido = {}
    real_dummy = CH.printer.Dummy

    def serial_falso(**kwargs):
        recibido.update(kwargs)
        return real_dummy()

    class FakeConfigberry:
        def get_config_for_printer(self, name):
            return {"driver": "Serial", "devfile": "COM3", "baudrate": "9600",
                    "timeout": "2", "_setup_id": "serial:067b:2303:PL1",
                    "_otro_metadato": "x"}

    monkeypatch.setattr(CH, "configberry", FakeConfigberry())
    monkeypatch.setattr(CH.printer, "Serial", serial_falso)

    response = CH.runTraductor(
        {"printerName": "Cocina", "printTexto": {"texto": "prueba"}},
        None,
    )

    assert response["message"] == "Impresión exitosa"
    assert recibido == {"devfile": "COM3", "baudrate": 9600, "timeout": 2.0}


@pytest.mark.parametrize("texto,valor", [("false", False), ("False", False), ("0", False),
                                         ("no", False), ("true", True), ("1", True),
                                         ("sí", True)])
def test_serial_lee_los_si_no_del_config(texto, valor, monkeypatch):
    """bool("false") es True: un `dsrdtr = false` activaba el control de flujo."""
    recibido = {}
    monkeypatch.setattr(CH.printer, "Serial", lambda **kw: recibido.update(kw) or object())
    CH.build_driver({"driver": "Serial", "devfile": "COM3", "dsrdtr": texto,
                     "xonxoff": texto, "bytesize": "7", "stopbits": "1.5"})
    assert recibido["dsrdtr"] is valor and recibido["xonxoff"] is valor
    assert recibido["bytesize"] == 7 and recibido["stopbits"] == 1.5


def test_serial_con_un_si_no_invalido_es_un_error_claro(monkeypatch):
    monkeypatch.setattr(CH.printer, "Serial", lambda **kw: object())
    with pytest.raises(CH.DriverError, match="dsrdtr"):
        CH.build_driver({"driver": "Serial", "devfile": "COM3", "dsrdtr": "quizas"})
    assert CH.build_driver({"driver": "Serial", "devfile": "COM3", "stopbits": "2"})


def test_network_recibe_el_timeout_del_config_como_numero(monkeypatch):
    """
    Del config.ini todo llega como texto. python-escpos le pasa `timeout` a
    socket.settimeout(), que con "10" lanza TypeError y la impresión falla.
    """
    recibido = {}
    real_dummy = CH.printer.Dummy

    def network_falso(**kwargs):
        import socket
        socket.socket().settimeout(kwargs["timeout"])  # lo que hace escpos
        recibido.update(kwargs)
        return real_dummy()

    class FakeConfigberry:
        def get_config_for_printer(self, name):
            return {"driver": "Network", "host": "192.168.1.80",
                    "port": "9100", "timeout": "10"}

    monkeypatch.setattr(CH, "configberry", FakeConfigberry())
    monkeypatch.setattr(CH.printer, "Network", network_falso)

    response = CH.runTraductor(
        {"printerName": "Barra", "printTexto": {"texto": "prueba"}},
        None,
    )

    assert response["message"] == "Impresión exitosa"
    assert recibido["timeout"] == 10.0
    assert recibido["port"] == 9100


# ---------------------------------------------------------------------------
# Issue #166: comandos remotos "imprimir todos" / "descartar" sobre la cola.
# ---------------------------------------------------------------------------

def test_imprimir_pendientes_command_requeues_failed(fake_spooler):
    fake_spooler._failed.add("job-failed-1")

    handler = CH.ComandosHandler()
    resp = handler.send_command({"imprimirPendientes": True})

    assert fake_spooler.requeue_failed_calls == 1
    # Mismo formato que el resto de los comandos genéricos (getStatus, etc.):
    # {"rta": {"action": ..., "rta": {...datos...}}}
    action_response = resp["rta"]
    assert action_response["action"] == "imprimirPendientes"
    r = action_response["rta"]
    assert r["requeued"] == 1
    assert r["pending_count"] == 1
    assert r["failed_count"] == 0


def test_descartar_pendientes_command_discards_everything(fake_spooler):
    fake_spooler.enqueue("job-1", {"a": 1}, "cocina")
    fake_spooler._failed.add("job-failed-1")

    handler = CH.ComandosHandler()
    resp = handler.send_command({"descartarPendientes": True})

    assert fake_spooler.discard_all_calls == 1
    action_response = resp["rta"]
    assert action_response["action"] == "descartarPendientes"
    r = action_response["rta"]
    assert r["discarded"] == 2
    assert r["pending_count"] == 0
    assert r["failed_count"] == 0


def test_imprimir_pendientes_with_nothing_pending_is_a_noop(fake_spooler):
    handler = CH.ComandosHandler()
    resp = handler.send_command({"imprimirPendientes": True})

    r = resp["rta"]["rta"]
    assert r["requeued"] == 0
    assert r["pending_count"] == 0
    assert r["failed_count"] == 0


def test_shutdown_print_spooler_stops_and_clears_singleton_if_created(fake_spooler):
    """shutdown_print_spooler() (cierre ordenado, issue #165 propuesta 3) debe
    llamar a stop() sobre el spooler existente y dejar el singleton en None,
    sin crear uno nuevo si nunca se usó."""
    fake_spooler.stop_calls = 0
    fake_spooler.stop = lambda: setattr(
        fake_spooler, "stop_calls", fake_spooler.stop_calls + 1)

    CH.shutdown_print_spooler()

    assert fake_spooler.stop_calls == 1
    assert CH._print_spooler is None


def test_shutdown_print_spooler_is_noop_when_never_created(monkeypatch):
    """Si nunca se llamó a get_print_spooler(), shutdown_print_spooler() no
    debe instanciar uno (evita crear un .db real solo para cerrarlo)."""
    monkeypatch.setattr(CH, "_print_spooler", None)
    created = []
    monkeypatch.setattr(
        CH, "get_print_spooler",
        lambda: created.append(True) or None)

    CH.shutdown_print_spooler()

    assert created == []
    assert CH._print_spooler is None
