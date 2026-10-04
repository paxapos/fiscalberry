"""
paxapos/fiscalberry#158: el QR de la factura electronica (RG 4291) hardcodeaba
moneda="PES"/ctz=1 ignorando encabezado.moneda/encabezado.ctz. Verifica que el
QR use los valores del encabezado cuando vienen, y mantenga el default PES/1
para retrocompatibilidad con encabezados que no los mandan.
"""

import base64
import json

from escpos.escpos import EscposIO
from escpos.printer import Dummy

from fiscalberry.common.EscPComandos import EscPComandos


def _encabezado_base(**overrides):
    encabezado = {
        "nombre_comercio": "Paxapoga",
        "razon_social": "Riotorno SRL",
        "cuit_empresa": "30715582593",
        "domicilio_comercial": "Beruti 4643",
        "tipo_responsable": "Resp. Inscripto",
        "inicio_actividades": "",
        "tipo_comprobante": '"B"',
        "tipo_comprobante_codigo": "006",
        "numero_comprobante": "0010-00011795",
        "fecha_comprobante": "2024-08-29",
        "documento_cliente": "0",
        "nombre_cliente": "",
        "domicilio_cliente": "",
        "nombre_tipo_documento": "Sin identificar",
        "cae": "74353157058451",
        "cae_vto": "2024-09-08",
        "importe_total": "1.00",
        "importe_neto": "0.83",
        "importe_iva": "0.17",
    }
    encabezado.update(overrides)
    return encabezado


def test_qr_usa_moneda_y_ctz_del_encabezado_cuando_vienen(monkeypatch):
    capturado = {}

    def _fake_qr(self, content, *args, **kwargs):
        capturado["data"] = content

    monkeypatch.setattr(Dummy, "qr", _fake_qr, raising=True)

    printer = Dummy()
    comandos = EscPComandos(printer)
    with EscposIO(printer, autocut=False, autoclose=False) as escpos:
        ok = comandos.printFacturaElectronica(
            escpos,
            encabezado=_encabezado_base(moneda="DOL", ctz=1350.5),
            items=[{"alic_iva": 0.21, "importe": 1, "ds": "Producto", "qty": 1}],
            pagos=[],
        )
    assert ok is True

    payload_b64 = capturado["data"].split("?p=", 1)[1]
    qr = json.loads(base64.decodebytes(payload_b64.encode()))

    assert qr["moneda"] == "DOL"
    assert qr["ctz"] == 1350.5


def test_qr_default_pes_1_cuando_encabezado_no_manda_moneda_ni_ctz(monkeypatch):
    capturado = {}

    def _fake_qr(self, content, *args, **kwargs):
        capturado["data"] = content

    monkeypatch.setattr(Dummy, "qr", _fake_qr, raising=True)

    printer = Dummy()
    comandos = EscPComandos(printer)
    encabezado = _encabezado_base()
    assert "moneda" not in encabezado and "ctz" not in encabezado

    with EscposIO(printer, autocut=False, autoclose=False) as escpos:
        ok = comandos.printFacturaElectronica(
            escpos,
            encabezado=encabezado,
            items=[{"alic_iva": 0.21, "importe": 1, "ds": "Producto", "qty": 1}],
            pagos=[],
        )
    assert ok is True

    payload_b64 = capturado["data"].split("?p=", 1)[1]
    qr = json.loads(base64.decodebytes(payload_b64.encode()))

    assert qr["moneda"] == "PES"
    assert qr["ctz"] == 1
