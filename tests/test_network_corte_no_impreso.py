# coding=utf-8
"""
printRaw por Network (paxapos/fiscalberry#223): si la impresora corta la
conexión antes de leer todo el ticket, no puede darse por impreso.

sendall() vuelve apenas los bytes entran al buffer del socket, así que el corte
no se ve al escribir. Una impresora sana que no contesta ni cierra, o que cierra
después de leer todo, sigue siendo OK.
"""

import base64
import gzip
import socket
import threading

import pytest

from fiscalberry.common import ComandosHandler as ch

TICKET = b"\x1b@" + b"REMITO 0001-00001234\n" * 22 + b"\x1dV\x00"


class Impresora:
    """Impresora de red falsa en 127.0.0.1: lee hasta `lee` bytes y cierra; sin
    `lee`, hasta que el cliente cierra. Si cierra con datos sin leer, el sistema
    le manda un RST al cliente."""

    def __init__(self, lee=None):
        self.srv = socket.create_server(("127.0.0.1", 0))
        self.port = self.srv.getsockname()[1]
        self.recibido = b""
        self.hilo = threading.Thread(target=self._atender, args=(lee,), daemon=True)
        self.hilo.start()

    def _atender(self, lee):
        conn, _ = self.srv.accept()
        with conn:
            while lee is None or len(self.recibido) < lee:
                trozo = conn.recv(lee - len(self.recibido) if lee else 4096)
                if not trozo:
                    break
                self.recibido += trozo
        self.srv.close()


@pytest.fixture
def imprimir(monkeypatch):
    monkeypatch.setattr(ch.PrinterErrorDetector, "detect_and_publish_error",
                        classmethod(lambda cls, **kw: ("X", "x")))

    def imprimir(impresora):
        monkeypatch.setattr(ch.configberry, "get_config_for_printer", lambda nombre: {
            "driver": "Network", "host": "127.0.0.1", "port": str(impresora.port), "timeout": "5"})
        cmd = {"data": base64.b64encode(gzip.compress(TICKET)).decode()}
        return ch.runTraductor({"printerName": "caja", "printRaw": cmd}, None)

    return imprimir


def test_corte_a_mitad_no_se_da_por_impreso(imprimir):
    impresora = Impresora(lee=200)

    with pytest.raises(OSError):
        imprimir(impresora)
    assert len(impresora.recibido) == 200


@pytest.mark.parametrize("lee", [None, len(TICKET)], ids=["no-contesta", "cierra-tras-leer-todo"])
def test_impresora_sana_es_ok(imprimir, lee):
    impresora = Impresora(lee=lee)

    rta = imprimir(impresora)

    impresora.hilo.join(2)
    assert rta["result"] == "ok"
    assert impresora.recibido == TICKET
