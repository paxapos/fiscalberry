# coding=utf-8
"""
Factura electronica en moneda extranjera (seguimiento de #158).

El encabezado (neto/iva/total) ya viene en la moneda del comprobante, pero los
items, el descuento y el desglose de IVA del payload son el snapshot de la venta
en la moneda funcional: sin convertirlos el papel quedaba internamente
inconsistente (items en pesos, TOTAL en dolares) y sin la moneda/cotizacion a la
vista. Estos tests fijan:

  * el ticket en pesos (con o sin las claves moneda/ctz) NO cambia ni un byte;
  * en moneda extranjera se convierten items, descuento e IVA, y aparece la
    linea "Moneda: ... - Cotiz: ...";
  * moneda/ctz nulos caen al default local;
  * ctz numerico en el QR aunque el payload lo mande como string (RG 4291).

El golden de bytes se regenera renderizando el caso base con Dummy() y volcando
base64.b64encode(printer.output).
"""

import base64
import hashlib
import json

import pytest
from escpos.escpos import EscposIO
from escpos.printer import Dummy

from fiscalberry.common.EscPComandos import EscPComandos, convertirDesdeBase


ENCABEZADO_BASE = {
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
    "importe_total": "121.00",
    "importe_neto": "100.00",
    "importe_iva": "21.00",
}

# Cotizacion de la prueba: 1 unidad de moneda extranjera = 1350,50 de la local.
CTZ = 1350.5

# Items del snapshot: en pesos valen qty x importe; en la moneda del comprobante
# dan 60,50 y 2 x 30,25 => 121,00, que es exactamente el importe_total.
ITEMS_PESOS = [
    {"alic_iva": 21.0, "importe": 81705.25, "ds": "Milanesa napolitana", "qty": 1},
    {"alic_iva": 21.0, "importe": 40852.63, "ds": "Gaseosa", "qty": 2},
]
IVAS_PESOS = [{"alic_iva": "21.00", "importe": 28360.5}]
PAGOS = [{"ds": "Efectivo", "importe": "121.00"}]

# Mismos importes ya expresados en la moneda del comprobante (caso en pesos).
ITEMS_BASE = [
    {"alic_iva": 21.0, "importe": 60.5, "ds": "Milanesa napolitana", "qty": 1},
    {"alic_iva": 21.0, "importe": 30.25, "ds": "Gaseosa", "qty": 2},
]
IVAS_BASE = [{"alic_iva": "21.00", "importe": "21.00"}]
ADD_ADDITIONAL_BASE = {
    "amount": "10.00",
    "description": "Descuento",
    "descuento_porcentaje": "10",
}
ADD_ADDITIONAL_PESOS = {
    "amount": "13505.00",
    "description": "Descuento",
    "descuento_porcentaje": "10",
}

# Bytes ESC/POS del caso base (comprobante en moneda local, sin claves
# moneda/ctz) tal como los emitia el cliente antes de este cambio.
GOLDEN_BASE_B64 = (
    "GyEAGyEAGyEAG3sAHWIAG0UAGy0AG00AG2EAHUIAG0UBG00AG2EBG3QAUGF4YXBvZ2EK"
    "ChshABshABshABtNABthAFJpb3Rvcm5vIFNSTApDVUlUOiAzMDcxNTU4MjU5MwpCZXJ1"
    "dGkgNDY0MwpJbmljaW8gZGUgYWN0aXZpZGFkZXM6IApSZXNwLiBJbnNjcmlwdG8KG00A"
    "G2EBLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQobRQEbTQAb"
    "YQEiQiIgTnJvLiAwMDEwLTAwMDExNzk1CkZlY2hhIDIwMjQtMDgtMjkKG00AG2EBLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQpBIENvbnN1bWlkb3Ig"
    "RmluYWwgCj09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KG0UB"
    "G00AG2EAQ0FOVCAgICAgICAgICBERVNDUklQQ0kbdA3gTiAgICAgICAgIFBSRUNJTwoK"
    "GyEAGyEAGyEAG00AG2EAGyEAGyEAGyEAG00AG2EAMSAgICAgTWlsYW5lc2EgbmFwb2xp"
    "dGFuYSAgICAgICAgICA2MC41MAobIQAbIQAbIQAbTQAbYQAyICAgICBHYXNlb3NhICAg"
    "ICAgICAgICAgICAgICAgICAgIDYwLjUwCi0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0t"
    "LS0tLS0tLS0tLS0tLS0KGyEAGyEAGyEwG0UBG2EBVE9UQUw6ICQxMjEuMDAKChshABsh"
    "ABshABtNABthAC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0K"
    "GyEAGyEAGyEAG0UBG00BG2EBVHJhbnNwYXJlbmNpYSBGaXNjYWwgKExleSAyNy43NDMp"
    "ChshABshABshABtNABthAElWQSBDb250ZW5pZG86ICAgICAgICAgICAgICQgICAgICAg"
    "MjEuMDAKChshABshABshABtFABtNARthABtFAVJlY2liaW1vczoKGyEAGyEAGyEAG00A"
    "G2EARUZFQ1RJVk8gICAgICAgICAgICAgICAgICAgICAgICAgIDEyMS4wMAobIQAbIQAb"
    "IQAbTQAbYQAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCgob"
    "TQAbYQEbTQAbYQFDb21wcm9iYW50ZSBBdXRvcml6YWRvIHBvciBBRklQCmh0dHBzOi8v"
    "d3d3LmFmaXAuZ29iLmFyL2ZlL3FyLz9wPWV5SjJaWElpT2lBeExDQWlabVZqYUdFaU9p"
    "QWlNamt0TURndE1qQXlOQ0lzSUNKamRXbDBJam9nTXpBM01UVTFPREkxT1RNc0lDSndk"
    "RzlXZEdFaU9pQXhNQ3dnSW5ScGNHOURiWEFpT2lBMkxDQWlibkp2UTIxd0lqb2dNVEUz"
    "T1RVc0lDSnBiWEJ2Y25SbElqb2dNVEl4TGpBc0lDSnRiMjVsWkdFaU9pQWlVRVZUSWl3"
    "Z0ltTjBlaUk2SURFc0lDSjBhWEJ2UTI5a1FYVjBJam9nSWtVaUxDQWlZMjlrUVhWMElq"
    "b2dOelF6TlRNeE5UY3dOVGcwTlRGORtNABthAQpDQUU6IDc0MzUzMTU3MDU4NDUxICAg"
    "IENBRSBWVE86IDIwMjQtMDktMDgKRmVjaGEgeSBob3JhIGRlIGltcHJlc2lvbjogChtF"
    "ARtNABthAQoqKiBTb2Z0d2FyZSBQQVhBUE9TICoqG2QGHVYA"
)

# sha256 de los otros dos tickets en moneda local que tambien deben quedar
# congelados: con descuento y con detalle de IVAs (Factura A).
SHA_BASE_CON_DESCUENTO = "e66da985bb455f775bee1f24f9040446062d5862d0ae0dddb87cdae9d9638fee"
SHA_BASE_INSCRIPTO = "9cbeac3954331c0f167ba4098287a98641754e3d7e99604ae720bb7d0c451feb"

ENCABEZADO_INSCRIPTO = {
    "tipo_comprobante": "Factura A",
    "tipo_comprobante_codigo": "001",
    "nombre_cliente": "Juan",
    "documento_cliente": "20111111112",
    "nombre_tipo_documento": "CUIT",
}


@pytest.fixture(autouse=True)
def qr_como_texto(monkeypatch):
    """El QR se imprime como texto para que su contenido entre en la comparacion
    de bytes (el raster depende de la libreria de imagenes, no del formato)."""

    def _fake_qr(self, content, *args, **kwargs):
        self.text(content)

    monkeypatch.setattr(Dummy, "qr", _fake_qr, raising=True)


def render(encabezado=None, items=None, ivas=None, **kwargs):
    enc = dict(ENCABEZADO_BASE)
    enc.update(encabezado or {})
    printer = Dummy()
    comandos = EscPComandos(printer)
    with EscposIO(printer, autocut=False, autoclose=False) as escpos:
        ok = comandos.printFacturaElectronica(
            escpos,
            encabezado=enc,
            items=ITEMS_BASE if items is None else items,
            ivas=IVAS_BASE if ivas is None else ivas,
            pagos=PAGOS,
            **kwargs,
        )
    assert ok is True
    return printer.output


def qr_del_ticket(salida):
    payload = salida.split(b"?p=", 1)[1].split(b"\x1b", 1)[0]
    return json.loads(base64.decodebytes(payload))


# ---------------------------------------------------------------------------
# (a) retrocompatibilidad: el ticket en moneda local no cambia
# ---------------------------------------------------------------------------


def test_moneda_local_sin_claves_bytes_identicos_al_legacy():
    assert render() == base64.b64decode(GOLDEN_BASE_B64)


def test_moneda_local_con_pes_y_ctz_1_bytes_identicos_al_legacy():
    assert render(encabezado={"moneda": "PES", "ctz": 1}) == base64.b64decode(GOLDEN_BASE_B64)


def test_moneda_local_con_descuento_y_con_detalle_de_ivas_no_cambian():
    con_descuento = render(addAdditional=ADD_ADDITIONAL_BASE)
    inscripto = render(encabezado=ENCABEZADO_INSCRIPTO)

    assert hashlib.sha256(con_descuento).hexdigest() == SHA_BASE_CON_DESCUENTO
    assert hashlib.sha256(inscripto).hexdigest() == SHA_BASE_INSCRIPTO


# ---------------------------------------------------------------------------
# (b) moneda extranjera: cuerpo convertido + linea de moneda/cotizacion
# ---------------------------------------------------------------------------


def test_moneda_extranjera_convierte_items_descuento_e_iva():
    salida = render(
        encabezado={"moneda": "DOL", "ctz": CTZ},
        items=ITEMS_PESOS,
        ivas=IVAS_PESOS,
        addAdditional=ADD_ADDITIONAL_PESOS,
    )

    # items: 81.705,25 / 1350,50 = 60,50 y 40.852,63 / 1350,50 = 30,25 (x2)
    assert b"Milanesa napolitana" in salida
    assert salida.count(b"60.50") >= 2
    assert b"81,705.25" not in salida and b"40,852.63" not in salida

    # los dos items suman el TOTAL del encabezado
    assert b"TOTAL: $121.00" in salida

    # descuento: 13.505,00 / 1350,50 = 10,00 (subtotal = 121,00 + 10,00)
    assert b"$      -10.00" in salida
    assert b"$      131.00" in salida
    assert b"13,505.00" not in salida

    # IVA de la transparencia fiscal: 28.360,50 / 1350,50 = 21,00
    assert b"IVA Contenido:" in salida
    assert b"28,360.50" not in salida

    # cara del comprobante: moneda y cotizacion visibles (codigo AFIP -> ISO)
    assert b"Moneda: USD - Cotiz: $1,350.50" in salida

    qr = qr_del_ticket(salida)
    assert qr["moneda"] == "DOL"
    assert qr["ctz"] == CTZ


def test_moneda_local_no_imprime_linea_de_moneda():
    assert b"Moneda:" not in render()


# ---------------------------------------------------------------------------
# (c) moneda/ctz nulos: default a la moneda local
# ---------------------------------------------------------------------------


def test_moneda_y_ctz_nulos_caen_al_default_local():
    salida = render(encabezado={"moneda": None, "ctz": None})

    assert salida == base64.b64decode(GOLDEN_BASE_B64)

    qr = qr_del_ticket(salida)
    assert qr["moneda"] == "PES"
    assert qr["ctz"] == 1


# ---------------------------------------------------------------------------
# (d) ctz como string en el payload: el QR igual sale numerico (RG 4291)
# ---------------------------------------------------------------------------


def test_ctz_string_sale_numerico_en_el_qr():
    salida = render(
        encabezado={"moneda": "DOL", "ctz": "1350.50"},
        items=ITEMS_PESOS,
        ivas=IVAS_PESOS,
    )

    qr = qr_del_ticket(salida)
    assert not isinstance(qr["ctz"], str)
    assert qr["ctz"] == CTZ

    # y el string tambien sirve para convertir el cuerpo
    assert b"Moneda: USD - Cotiz: $1,350.50" in salida
    assert salida.count(b"60.50") >= 2


# ---------------------------------------------------------------------------
# conversion: mismo redondeo que la emision (half-up sobre el cociente)
# ---------------------------------------------------------------------------


def test_convertir_desde_base_redondea_half_up():
    assert convertirDesdeBase(81705.25, 1350.5) == 60.5
    assert convertirDesdeBase(40852.63, 1350.5) == 30.25
    assert convertirDesdeBase(1.005, 1) == 1.01
    assert convertirDesdeBase(-1.005, 1) == -1.01
    assert convertirDesdeBase(100, 0) == 100
