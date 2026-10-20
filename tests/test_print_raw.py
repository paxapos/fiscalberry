# coding=utf-8
"""
printRaw: paxapos renderiza los bytes ESC/POS y fiscalberry solo los escupe.

Lo que se fija acá es que el camino raw no pierda tickets en silencio: si el
driver falla (también en close(), que en CUPS / LP / Win32Raw es el que manda
el trabajo) tiene que LANZAR para que el spooler reintente.
"""

import base64
import gzip

import pytest

pytest.importorskip("paho")
pytest.importorskip("escpos")

import fiscalberry.common.ComandosHandler as CH  # noqa: E402

BYTES = b"\x1b@hola\n\x1dV\x00"


def _cmd(data=BYTES, encoding="gzip+base64"):
    if encoding == "base64":
        payload = base64.b64encode(data)
    else:
        payload = base64.b64encode(gzip.compress(data))
    return {"data": payload.decode("ascii"), "encoding": encoding}


class FakeDriver:
    def __init__(self, falla_raw=False, falla_close=False):
        self.recibido = b""
        self.cierres = 0
        self.falla_raw = falla_raw
        self.falla_close = falla_close

    def _raw(self, data):
        if self.falla_raw:
            raise OSError("impresora desconectada")
        self.recibido += data

    def close(self):
        self.cierres += 1
        if self.falla_close:
            raise OSError("cups rechazó el trabajo")


@pytest.fixture(autouse=True)
def sin_publicar(monkeypatch):
    publicados = []
    monkeypatch.setattr(CH.PrinterErrorDetector, "detect_and_publish_error",
                        classmethod(lambda cls, **kw: publicados.append(kw) or ("X", "x")))
    return publicados


@pytest.mark.parametrize("encoding", ["gzip+base64", "gzip", "base64"])
def test_decodifica_los_encodings_soportados(encoding):
    assert CH.decode_raw_payload(_cmd(encoding=encoding)) == BYTES


def test_sin_data_es_error():
    with pytest.raises(ValueError):
        CH.decode_raw_payload({"encoding": "gzip+base64"})


def test_imprime_y_cierra():
    drv = FakeDriver()

    rta = CH._print_raw(drv, _cmd(), "cocina", "Network")

    assert drv.recibido == BYTES
    assert drv.cierres == 1
    assert rta["bytes"] == len(BYTES)


def test_fallo_del_driver_lanza_cierra_y_publica(sin_publicar):
    drv = FakeDriver(falla_raw=True)

    with pytest.raises(OSError):
        CH._print_raw(drv, _cmd(), "cocina", "Network")

    assert drv.cierres == 1
    assert sin_publicar and sin_publicar[0]["context"]["command"] == "printRaw"


def test_fallo_en_close_no_se_reporta_como_ok():
    """Antes el close() se tragaba la excepción: en CUPS eso era un ticket perdido."""
    drv = FakeDriver(falla_close=True)

    with pytest.raises(OSError):
        CH._print_raw(drv, _cmd(), "caja", "CupsPrinter")
