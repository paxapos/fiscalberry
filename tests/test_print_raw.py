"""
printRaw: bytes ESC/POS que arma Paxapos (paxapos/fiscalberry#213, épica
paxapos/paxapos#1723). Un fallo al imprimirlos tiene que llegar al spooler como
excepción (para que reintente), nunca reportarse como impreso.
"""

import base64
import gzip

import pytest

from fiscalberry.common import ComandosHandler as ch
from fiscalberry.common.FiscalberryComandos import FiscalberryComandos, PrinterException


DATOS = b"\x1b!\x00hola\n\x1bd\x06\x1dV\x00"


def _cmd(encoding="gzip+base64", data=DATOS):
    if encoding == "base64":
        payload = base64.b64encode(data)
    else:
        payload = base64.b64encode(gzip.compress(data))
    return {"data": payload.decode(), "encoding": encoding}


class DriverFalso:
    def __init__(self, falla_raw=False, falla_close=False):
        self.escrito = b""
        self.cierres = 0
        self.falla_raw = falla_raw
        self.falla_close = falla_close

    def _raw(self, data):
        if self.falla_raw:
            raise OSError("impresora desconectada")
        self.escrito += data

    def close(self):
        self.cierres += 1
        if self.falla_close:
            raise OSError("CUPS rechazó el trabajo")


@pytest.fixture
def publicados(monkeypatch):
    lista = []
    monkeypatch.setattr(ch.PrinterErrorDetector, "detect_and_publish_error",
                        classmethod(lambda cls, **kw: lista.append(kw) or ("X", "x")))
    return lista


@pytest.mark.parametrize("encoding", ["gzip+base64", "gzip", "base64"])
def test_decodifica_los_tres_encodings(encoding):
    assert ch.decode_raw_payload(_cmd(encoding)) == DATOS


def test_sin_encoding_es_gzip_base64():
    cmd = _cmd()
    del cmd["encoding"]
    assert ch.decode_raw_payload(cmd) == DATOS


@pytest.mark.parametrize("cmd", [{}, {"data": ""}, None, {"data": "eA==", "encoding": "zip"}])
def test_sin_data_o_encoding_desconocido_lanza(cmd):
    with pytest.raises(ValueError):
        ch.decode_raw_payload(cmd)


def test_imprime_y_cierra_una_vez(publicados):
    driver = DriverFalso()
    rta = ch._print_raw(driver, _cmd(), "Caja", "Network")
    assert driver.escrito == DATOS
    assert driver.cierres == 1
    assert rta["result"] == "ok" and rta["bytes"] == len(DATOS)
    assert publicados == []


def test_si_raw_falla_cierra_publica_y_relanza(publicados):
    driver = DriverFalso(falla_raw=True)
    with pytest.raises(OSError):
        ch._print_raw(driver, _cmd(), "Caja", "Network")
    assert driver.cierres == 1
    assert publicados and publicados[0]["context"]["command"] == "printRaw"


def test_si_close_falla_no_se_reporta_como_impreso(publicados):
    # En CUPS / LP / Win32Raw el close() es el que manda el trabajo
    driver = DriverFalso(falla_close=True)
    with pytest.raises(OSError, match="CUPS"):
        ch._print_raw(driver, _cmd(), "Caja", "CupsPrinter")
    assert publicados


def test_datos_rotos_tambien_lanzan_y_cierran(publicados):
    driver = DriverFalso()
    with pytest.raises(Exception):
        ch._print_raw(driver, {"data": "no-es-base64-gzip!!"}, "Caja", "Network")
    assert driver.cierres == 1
    assert driver.escrito == b""


def test_proxy_fiscalberry_propaga_el_error_del_remoto(monkeypatch, publicados):
    monkeypatch.setattr(ch.configberry, "get_config_for_printer",
                        lambda nombre: {"driver": "Fiscalberry", "host": "http://10.0.0.9:12000", "printerName": "Cocina"})

    def remoto_caido(self, host, data):
        raise PrinterException("No se pudo conectar")

    monkeypatch.setattr(FiscalberryComandos, "run", remoto_caido)
    with pytest.raises(PrinterException):
        ch.runTraductor({"printerName": "proxy", "printRaw": _cmd()}, None)


def test_proxy_fiscalberry_reenvia_el_printraw_tal_cual(monkeypatch):
    monkeypatch.setattr(ch.configberry, "get_config_for_printer",
                        lambda nombre: {"driver": "Fiscalberry", "host": "http://10.0.0.9:12000", "printerName": "Cocina"})
    enviados = []
    monkeypatch.setattr(FiscalberryComandos, "run", lambda self, host, data: enviados.append((host, data)) or [])
    cmd = _cmd()
    rta = ch.runTraductor({"printerName": "proxy", "jobId": "x", "printRaw": cmd}, None)
    assert enviados == [("http://10.0.0.9:12000", {"printerName": "Cocina", "printRaw": cmd})]
    assert rta["result"] == []


def test_fiscalberry_comandos_lanza_si_el_remoto_no_contesta_200(monkeypatch):
    class Respuesta:
        status_code = 500

    monkeypatch.setattr(ch_requests(), "post", lambda *a, **k: Respuesta())
    with pytest.raises(PrinterException, match="500"):
        FiscalberryComandos().run("http://x", {})


def ch_requests():
    import fiscalberry.common.FiscalberryComandos as fc
    return fc.requests


def test_driver_invalido_dice_cual():
    with pytest.raises(ch.DriverError, match="Invalid driver: noexiste"):
        ch.build_driver({"driver": "noexiste"})
