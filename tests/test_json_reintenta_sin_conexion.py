# coding=utf-8
"""
Modo JSON contra una impresora de red apagada (paxapos/fiscalberry#221).

Si la conexión se rechaza no se imprimió nada: el spooler tiene que reintentar,
igual que con printRaw, y el ticket sale una vez cuando vuelve la impresora. Si
la impresora corta después de recibir parte del ticket sigue siendo un fallo
final ("impreso con errores"), sin reintento, para no reimprimir un ticket
parcial.
"""

import socket
import time

import escpos.printer.network as network
import pytest

from fiscalberry.common import ComandosHandler as ch
from fiscalberry.common.confirmacion_impresion import errores_en_resultado
from fiscalberry.common.print_spooler import DurablePrintSpooler
from fiscalberry.common.printer_circuit_breaker import PrinterCircuitBreaker

COMANDA = {"printComanda": {"comanda": {"id": 7, "platos": [{"cant": 1, "nombre": "Milanesa"}]}}}


class RedFalsa:
    """Reemplaza al módulo socket de printer.Network: rechaza las primeras
    `rechazos` conexiones (Connection refused) y guarda lo que llega por cada
    conexión aceptada. Con `corta_tras`, la conexión se corta (Broken pipe) al
    pasar esa cantidad de bytes."""

    AF_INET, SOCK_STREAM, SHUT_RDWR, error = (
        socket.AF_INET, socket.SOCK_STREAM, socket.SHUT_RDWR, OSError)

    def __init__(self):
        self.rechazos = 0
        self.corta_tras = None
        self.conexiones = []

    def socket(self, *_):
        return _Conexion(self)


class _Conexion:
    def __init__(self, red):
        self.red = red
        self.datos = None

    def settimeout(self, _):
        pass

    def connect(self, _):
        if self.red.rechazos:
            self.red.rechazos -= 1
            raise ConnectionRefusedError(111, "Connection refused")
        self.datos = bytearray()
        self.red.conexiones.append(self.datos)

    def sendall(self, msg):
        if self.red.corta_tras is not None and len(self.datos) + len(msg) > self.red.corta_tras:
            raise BrokenPipeError(32, "Broken pipe")
        self.datos += msg

    def shutdown(self, _):
        pass

    def close(self):
        pass


@pytest.fixture
def red(monkeypatch):
    red = RedFalsa()
    monkeypatch.setattr(network, "socket", red)
    monkeypatch.setattr(ch.configberry, "get_config_for_printer",
                        lambda nombre: {"driver": "Network", "host": "127.0.0.1", "port": "9100"})
    breaker = PrinterCircuitBreaker()
    monkeypatch.setattr("fiscalberry.common.printer_circuit_breaker.get_circuit_breaker",
                        lambda: breaker)
    monkeypatch.setattr(ch.PrinterErrorDetector, "detect_and_publish_error",
                        classmethod(lambda cls, **kw: ("X", "x")))
    return red


def _imprimir(tmp_path):
    """Encola la comanda en un spooler real y devuelve (éxitos, fallos)."""
    exitos, fallos = [], []
    sp = DurablePrintSpooler(ch._spooler_print_fn, db_path=str(tmp_path / "s.db"),
                             base_delay=0.001, max_delay=0.01, idle_wait=0.02,
                             on_success=lambda *a: exitos.append(a),
                             on_failure=lambda *a: fallos.append(a))
    try:
        sp.enqueue("j1", dict(COMANDA, printerName="cocina", jobId="j1"), "cocina")
        fin = time.time() + 5
        while not exitos and time.time() < fin:
            time.sleep(0.02)
        time.sleep(0.1)
    finally:
        sp.stop()
    return exitos, fallos


def test_conexion_rechazada_se_reintenta_y_sale_una_vez(red, tmp_path):
    red.rechazos = 2

    exitos, fallos = _imprimir(tmp_path)

    assert [f[4] for f in fallos] == [False, False], "dos intentos rechazados, ninguno final"
    assert len(exitos) == 1
    assert errores_en_resultado(exitos[0][2]) == [], "salió completo, no 'impreso con errores'"
    assert len(red.conexiones) == 1 and b"Milanesa" in red.conexiones[0]


def test_corte_despues_de_escribir_no_se_reintenta(red, tmp_path):
    red.corta_tras = 20

    exitos, fallos = _imprimir(tmp_path)

    assert fallos == []
    assert len(exitos) == 1 and errores_en_resultado(exitos[0][2]), "impreso con errores"
    assert len(red.conexiones) == 1 and red.conexiones[0], "llegó parte del ticket"
