# coding=utf-8
"""
printRaw: decodificación acotada, cierre del driver sin doble envío y errores
permanentes de payload (sin reintento ni cuenta en el circuit breaker).
"""

import base64
import gzip
import time

import pytest

from fiscalberry.common import ComandosHandler as ch
from fiscalberry.common.print_spooler import DurablePrintSpooler, PermanentJobError


def _b64gz(data):
    return base64.b64encode(gzip.compress(data)).decode()


# ---------------------------------------------------------------- decodificación

def test_payload_valido_chico():
    assert ch.decode_raw_payload({"data": _b64gz(b"COMANDA\n")}) == b"COMANDA\n"


def test_payload_que_expande_sobre_el_tope(monkeypatch):
    monkeypatch.setattr(ch, "MAX_RAW_DECODED_BYTES", 1024)
    cmd = {"data": _b64gz(b"\0" * 100_000)}
    with pytest.raises(ch.InvalidPayloadError, match="maximo"):
        ch.decode_raw_payload(cmd)


def test_payload_justo_en_el_tope_pasa(monkeypatch):
    monkeypatch.setattr(ch, "MAX_RAW_DECODED_BYTES", 1024)
    assert len(ch.decode_raw_payload({"data": _b64gz(b"a" * 1024)})) == 1024


def test_base64_sin_comprimir_sobre_el_tope(monkeypatch):
    monkeypatch.setattr(ch, "MAX_RAW_DECODED_BYTES", 10)
    cmd = {"data": base64.b64encode(b"x" * 11).decode(), "encoding": "base64"}
    with pytest.raises(ch.InvalidPayloadError):
        ch.decode_raw_payload(cmd)


def test_data_codificada_sobre_el_tope(monkeypatch):
    monkeypatch.setattr(ch, "MAX_RAW_ENCODED_BYTES", 16)
    with pytest.raises(ch.InvalidPayloadError, match="data"):
        ch.decode_raw_payload({"data": "A" * 20})


@pytest.mark.parametrize("data", ["no es base64!!", "abc", "ab\ncd==x"])
def test_base64_invalido(data):
    with pytest.raises(ch.InvalidPayloadError):
        ch.decode_raw_payload({"data": data})


def test_gzip_corrupto():
    with pytest.raises(ch.InvalidPayloadError):
        ch.decode_raw_payload({"data": base64.b64encode(b"esto no es gzip").decode()})


def test_gzip_truncado():
    truncado = gzip.compress(b"COMANDA\n" * 50)[:-8]
    with pytest.raises(ch.InvalidPayloadError):
        ch.decode_raw_payload({"data": base64.b64encode(truncado).decode()})


@pytest.mark.parametrize("cmd", [{}, {"data": ""}, None, {"data": 5}])
def test_vacio_o_tipo_invalido(cmd):
    with pytest.raises(ch.InvalidPayloadError):
        ch.decode_raw_payload(cmd)


def test_el_error_sigue_siendo_value_error():
    assert issubclass(ch.InvalidPayloadError, ValueError)
    assert issubclass(ch.InvalidPayloadError, PermanentJobError)


# --------------------------------------------------------- cierre sin doble envío

class FakeCups:
    """Imita CupsPrinter de python-escpos: _raw acumula, close() envía el
    trabajo pendiente; si close() falla, el trabajo sigue pendiente y un
    segundo close() lo reenvía."""

    def __init__(self):
        self.pending = False
        self.sent = 0
        self.fail_next = True

    def _raw(self, b):
        self.pending = True

    def close(self):
        if self.pending:
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("cups: server busy")
            self.sent += 1
            self.pending = False


@pytest.fixture
def publicados(monkeypatch):
    lista = []
    monkeypatch.setattr(ch.PrinterErrorDetector, "detect_and_publish_error",
                        classmethod(lambda cls, **kw: lista.append(kw) or ("X", "x")))
    return lista


def test_si_close_falla_no_se_reenvia_el_trabajo(publicados):
    d = FakeCups()
    with pytest.raises(RuntimeError, match="busy"):
        ch._print_raw(d, {"data": _b64gz(b"COMANDA\n")}, "cocina", "cups")
    assert d.sent == 0          # el fallo se informa y el spooler reintenta
    assert publicados


def test_un_reintento_envia_una_sola_vez(publicados):
    d = FakeCups()
    with pytest.raises(RuntimeError):
        ch._print_raw(d, {"data": _b64gz(b"COMANDA\n")}, "cocina", "cups")
    ch._print_raw(d, {"data": _b64gz(b"COMANDA\n")}, "cocina", "cups")
    assert d.sent == 1


# --------------------------------------------------- errores permanentes: spooler

def _esperar(cond, timeout=5.0):
    fin = time.time() + timeout
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def test_spooler_error_permanente_sin_reintento_y_fuera_de_la_cola(tmp_path):
    llamadas, fallos = [], []

    def print_fn(ticket):
        llamadas.append(ticket)
        raise ch.InvalidPayloadError("base64 invalido")

    db = str(tmp_path / "s.db")
    sp = DurablePrintSpooler(print_fn, db_path=db, base_delay=0.01, idle_wait=0.05,
                             on_failure=lambda *a: fallos.append(a))
    try:
        sp.enqueue("j1", {"printerName": "p"}, "p")
        assert _esperar(lambda: fallos)
        time.sleep(0.3)
        assert len(llamadas) == 1
        assert sp.pending_count() == 0 and sp.failed_count() == 0
        job_id, ticket, exc, intentos, final = fallos[0]
        assert job_id == "j1" and final is True and isinstance(exc, ch.InvalidPayloadError)
    finally:
        sp.stop()

    # un reinicio no lo vuelve a encolar
    sp2 = DurablePrintSpooler(lambda t: None, db_path=db, idle_wait=0.05)
    try:
        assert sp2.pending_count() == 0 and sp2.failed_count() == 0
    finally:
        sp2.stop()


def test_error_transitorio_sigue_reintentando(tmp_path):
    llamadas, fallos = [], []

    def print_fn(ticket):
        llamadas.append(1)
        raise OSError("impresora caida")

    sp = DurablePrintSpooler(print_fn, db_path=str(tmp_path / "s.db"), base_delay=0.001,
                             max_delay=0.01, idle_wait=0.02,
                             on_failure=lambda *a: fallos.append(a))
    try:
        sp.enqueue("j1", {"printerName": "p"}, "p")
        assert _esperar(lambda: len(llamadas) >= 2)
        assert sp.pending_count() == 1
        assert all(f[4] is False for f in fallos)
    finally:
        sp.stop()


# ----------------------------------------------------- errores permanentes: breaker

def test_payload_invalido_no_suma_al_circuit_breaker(monkeypatch):
    class Breaker:
        fallos = []

        def allow(self, n):
            return True

        def record_failure(self, n):
            self.fallos.append(n)

        def record_success(self, n):
            pass

    b = Breaker()
    monkeypatch.setattr("fiscalberry.common.printer_circuit_breaker.get_circuit_breaker",
                        lambda: b)

    def invalido(ticket, queue):
        raise ch.InvalidPayloadError("gzip invalido")

    monkeypatch.setattr(ch, "runTraductor", invalido)
    with pytest.raises(ch.InvalidPayloadError):
        ch._spooler_print_fn({"printerName": "cocina"})
    assert b.fallos == []

    monkeypatch.setattr(ch, "runTraductor", lambda t, q: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(OSError):
        ch._spooler_print_fn({"printerName": "cocina"})
    assert b.fallos == ["cocina"]


# ------------------------------------------------------------ comandos remotos

@pytest.fixture
def handler(monkeypatch):
    h = ch.ComandosHandler()
    llamados = []
    monkeypatch.setattr(h, "_rebootFiscalberry", lambda: llamados.append("reboot") or {"rta": 0})
    monkeypatch.setattr(h, "_restartService", lambda: llamados.append("restart") or {"rta": "ok"})
    monkeypatch.setattr(h, "_upgrade", lambda: llamados.append("upgrade") or {"rta": "ok"})
    h.llamados = llamados
    return h


def _config(monkeypatch, valor):
    monkeypatch.setattr(
        ch.configberry, "get",
        lambda sec, key, fallback=None: valor if key == "remote_power_commands" else fallback)


@pytest.mark.parametrize("cmd", ["reboot", "restart"])
def test_reboot_restart_apagados_por_defecto(handler, monkeypatch, cmd):
    _config(monkeypatch, "false")
    rta = handler.send_command({cmd: True})
    assert "deshabilitados" in rta["err"]
    assert handler.llamados == []


@pytest.mark.parametrize("cmd", ["reboot", "restart"])
@pytest.mark.parametrize("valor", [False, "true", 1, None, "false", 0])
def test_valor_distinto_de_true_se_ignora(handler, monkeypatch, cmd, valor):
    _config(monkeypatch, "true")
    rta = handler.send_command({cmd: valor})
    assert "err" in rta
    assert handler.llamados == []


@pytest.mark.parametrize("cmd", ["reboot", "restart"])
def test_reboot_restart_habilitados_por_config(handler, monkeypatch, cmd):
    _config(monkeypatch, "true")
    handler.send_command({cmd: True})
    assert handler.llamados == [cmd]


@pytest.mark.parametrize("valor", [False, "true", 1, None])
def test_upgrade_exige_true(handler, valor):
    rta = handler.send_command({"upgrade": valor})
    assert "err" in rta and handler.llamados == []


def test_upgrade_true_funciona_sin_opcion_local(handler, monkeypatch):
    _config(monkeypatch, "false")
    handler.send_command({"upgrade": True})
    assert handler.llamados == ["upgrade"]
