# coding=utf-8
"""
Drivers Cups y LP (paxapos/fiscalberry#220) con las clases reales de
python-escpos y una cups.Connection o un `lp` falsos: el trabajo tiene que
llegar a la cola una sola vez, y si CUPS no lo acepta, se le devuelve el error
al spooler para que lo reintente en vez de darlo por impreso.
"""

import base64
import gzip
import io
from types import SimpleNamespace

import pytest

cups = pytest.importorskip("cups")

from fiscalberry.common import ComandosHandler as ch
from fiscalberry.common.EscPComandos import EscPComandos
from fiscalberry.common.print_spooler import PermanentJobError
from escpos.printer import lp as escpos_lp

DATOS = b"\x1b@COMANDA\n\x1dV\x00"
CONFIG = {"driver": "Cups", "printer_name": "qa-raw"}


def _printraw():
    return {"data": base64.b64encode(gzip.compress(DATOS)).decode()}


@pytest.fixture
def cola(monkeypatch):
    """Cola CUPS falsa: `trabajos` guarda lo que llega; `fallas` es cuántos
    printFile seguidos fallan antes de aceptar."""
    estado = SimpleNamespace(trabajos=[], fallas=0)

    class Conexion:
        def getPrinters(self):
            return {"qa-raw": {"printer-state": 3}}

        def getDefault(self):
            return "qa-raw"

        def printFile(self, nombre, archivo, titulo, opciones):
            if estado.fallas:
                estado.fallas -= 1
                raise cups.IPPError(1287, "printer not accepting jobs")
            with open(archivo, "rb") as f:
                estado.trabajos.append(f.read())
            return len(estado.trabajos)

    monkeypatch.setattr(cups, "Connection", Conexion)
    monkeypatch.setattr(cups, "setServer", lambda *a: None)
    monkeypatch.setattr(cups, "setPort", lambda *a: None)
    monkeypatch.setattr(ch.PrinterErrorDetector, "detect_and_publish_error",
                        classmethod(lambda cls, **kw: ("X", "x")))
    return estado


def _driver():
    return ch.build_driver(dict(CONFIG))[0]


def _imprimir_raw(driver):
    ch._print_raw(driver, _printraw(), "qa_cups", "CupsPrinter")


def _imprimir_json(driver):
    EscPComandos(driver).run({"printTexto": "hola"})


def test_printraw_llega_a_cups_una_vez(cola):
    _imprimir_raw(_driver())
    assert cola.trabajos == [DATOS]


def test_json_llega_a_cups_una_vez(cola):
    _imprimir_json(_driver())
    assert len(cola.trabajos) == 1 and b"hola" in cola.trabajos[0]


@pytest.mark.parametrize("imprimir", [_imprimir_raw, _imprimir_json], ids=["printRaw", "json"])
def test_si_printfile_falla_se_reintenta_y_llega_una_vez(imprimir, cola):
    """printFile falla una vez y después anda: un solo trabajo en la cola."""
    cola.fallas = 1
    fallido = _driver()
    with pytest.raises(Exception) as fallo:
        imprimir(fallido)
    assert not isinstance(fallo.value, PermanentJobError), "el spooler lo tiene que reintentar"
    fallido.close()  # lo mismo que hace Escpos.__del__ al destruir el driver
    assert cola.trabajos == []

    imprimir(_driver())  # el reintento del spooler crea un driver nuevo
    assert len(cola.trabajos) == 1


def test_cola_inexistente_no_se_da_por_impresa(cola):
    with pytest.raises(ch.DriverError):
        ch.build_driver({"driver": "Cups", "printer_name": "no-existe"})


@pytest.fixture
def lp(monkeypatch):
    """`lp` falso que termina con `codigo` (1 = p. ej. la cola no acepta trabajos)."""
    estado = SimpleNamespace(codigo=0)

    class Proceso:
        def __init__(self, args, **kw):
            self.stdin = io.BytesIO()
            self.returncode = None

        def wait(self):
            self.returncode = estado.codigo
            return self.returncode

        def terminate(self):
            pass

    monkeypatch.setattr(escpos_lp.LP, "printers", property(lambda self: {"qa-raw": "x"}))
    monkeypatch.setattr(escpos_lp.subprocess, "Popen", Proceso)
    return estado


def _driver_lp():
    return ch.build_driver({"driver": "LP", "printer_name": "qa-raw"})[0]


def test_lp_que_anda_cierra_sin_error(lp):
    d = _driver_lp()
    d._raw(DATOS)
    d.close()


def test_lp_que_falla_no_se_da_por_impreso(lp):
    lp.codigo = 1
    d = _driver_lp()
    d._raw(DATOS)
    with pytest.raises(OSError, match="lp"):
        d.close()
