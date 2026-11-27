# coding=utf-8
"""
Driver proxy Fiscalberry con un remoto que no contesta (paxapos/fiscalberry#222).

Si el remoto aceptó la conexión y recibió el ticket pero no contestó a tiempo,
puede haberlo impreso: reintentar lo duplicaría, así que es un fallo final. Si
no se pudo conectar, no se mandó nada y se reintenta como cualquier impresora
caída.
"""

import http.server
import json
import threading
import time

import pytest

from fiscalberry.common import ComandosHandler as ch
from fiscalberry.common.FiscalberryComandos import FiscalberryComandos
from fiscalberry.common.print_spooler import DurablePrintSpooler, PermanentJobError
from fiscalberry.common.printer_circuit_breaker import PrinterCircuitBreaker

TICKET = {"printRaw": {"data": "H4sIAAAAAAAAA8vIz8kBAAOWMa0DAAAA"}}


class _Atender(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.server.posts.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        if self.server.mudo:
            self.server.fin.wait(5)
            return
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


class Remoto(http.server.ThreadingHTTPServer):
    """Fiscalberry remoto falso en 127.0.0.1: rechaza la conexión hasta
    prender(); después guarda cada POST y contesta 200 o, si `mudo`, nada."""

    daemon_threads = True

    def __init__(self, mudo=False):
        self.mudo, self.posts, self.fin = mudo, [], threading.Event()
        super().__init__(("127.0.0.1", 0), _Atender, bind_and_activate=False)
        self.server_bind()
        self.url = "http://127.0.0.1:%d/" % self.server_address[1]

    def prender(self):
        self.server_activate()
        self.hilo = threading.Thread(target=self.serve_forever, daemon=True)
        self.hilo.start()

    def apagar(self):
        self.fin.set()
        if getattr(self, "hilo", None):
            self.shutdown()
        self.server_close()


@pytest.fixture
def remoto(monkeypatch):
    creados = []

    def crear(mudo=False):
        r = Remoto(mudo)
        creados.append(r)
        monkeypatch.setattr(ch.configberry, "get_config_for_printer", lambda nombre: {
            "driver": "Fiscalberry", "host": r.url, "printerName": "remota"})
        return r

    breaker = PrinterCircuitBreaker()
    monkeypatch.setattr("fiscalberry.common.printer_circuit_breaker.get_circuit_breaker",
                        lambda: breaker)
    monkeypatch.setattr(ch.PrinterErrorDetector, "detect_and_publish_error",
                        classmethod(lambda cls, **kw: ("X", "x")))
    yield crear
    for r in creados:
        r.apagar()


def _imprimir(tmp_path, al_fallar=lambda fallos: None, espera=0.0):
    """Encola el ticket en un spooler real y devuelve (éxitos, fallos)."""
    exitos, fallos = [], []

    def on_failure(*a):
        fallos.append(a)
        al_fallar(fallos)

    sp = DurablePrintSpooler(ch._spooler_print_fn, db_path=str(tmp_path / "s.db"),
                             base_delay=0.001, max_delay=0.01, idle_wait=0.02,
                             on_success=lambda *a: exitos.append(a), on_failure=on_failure)
    try:
        sp.enqueue("j1", dict(TICKET, printerName="proxy", jobId="j1"), "proxy")
        fin = time.time() + 5
        while not exitos and not any(f[4] for f in fallos) and time.time() < fin:
            time.sleep(0.02)
        time.sleep(espera)
    finally:
        sp.stop()
    return exitos, fallos


def test_remoto_que_no_contesta_es_fallo_final_sin_reintento(remoto, tmp_path, monkeypatch):
    monkeypatch.setattr(FiscalberryComandos, "timeout", (5, 0.3))
    r = remoto(mudo=True)
    r.prender()

    exitos, fallos = _imprimir(tmp_path, espera=1.0)

    assert len(r.posts) == 1, "un solo POST: el remoto ya lo recibió"
    assert exitos == []
    assert len(fallos) == 1
    _, _, exc, intentos, final = fallos[0]
    assert final is True and intentos == 1
    assert isinstance(exc, PermanentJobError) and "no se reintenta" in str(exc)


def test_remoto_que_rechaza_la_conexion_se_reintenta_y_sale_una_vez(remoto, tmp_path):
    r = remoto()

    def prender_al_segundo_fallo(fallos):
        if len(fallos) == 2:
            r.prender()

    exitos, fallos = _imprimir(tmp_path, al_fallar=prender_al_segundo_fallo, espera=0.1)

    assert [f[4] for f in fallos] == [False, False], "dos rechazos, ninguno final"
    assert len(exitos) == 1
    assert r.posts == [dict(TICKET, printerName="remota")]
