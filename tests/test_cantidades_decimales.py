# coding=utf-8
"""
Cantidades con hasta 4 decimales en factura, remito y pedido (issue #195).

El servidor puede mandar cantidades como 0.125 kg o 3.3751 lts. `floatToString`
(2 decimales, pensada para importes) las redondeaba: 0.125 salia "0.13". Estos
tests fijan que:

  * `cantidadToString` imprime hasta 4 decimales sin ceros colgantes;
  * `floatToString` (importes) NO cambia;
  * factura, remito y pedido imprimen la cantidad exacta;
  * la columna CANT no trunca la cantidad ni se pega a la descripcion, y el
    PRECIO queda alineado (papel de 80mm y de 58mm).
"""

import re

import pytest
from escpos.escpos import EscposIO
from escpos.printer import Dummy

from fiscalberry.common.EscPComandos import EscPComandos, cantidadToString, floatToString


ENCABEZADO_FACTURA_B = {
    "nombre_comercio": "Comercio de Prueba",
    "razon_social": "Comercio de Prueba SRL",
    "cuit_empresa": "30000000000",
    "domicilio_comercial": "Calle Falsa 123",
    "tipo_responsable": "Resp. Inscripto",
    "inicio_actividades": "",
    "tipo_comprobante": '"B"',
    "tipo_comprobante_codigo": "006",
    "numero_comprobante": "0001-00000001",
    "fecha_comprobante": "2024-08-29",
    "documento_cliente": "0",
    "nombre_cliente": "",
    "domicilio_cliente": "",
    "nombre_tipo_documento": "Sin identificar",
    "cae": "70000000000000",
    "cae_vto": "2024-09-08",
    "importe_total": "100.00",
    "importe_neto": "82.64",
    "importe_iva": "17.36",
}

ENCABEZADO_FACTURA_A = dict(
    ENCABEZADO_FACTURA_B,
    tipo_comprobante="Factura A",
    tipo_comprobante_codigo="001",
    nombre_cliente="Cliente de Prueba",
    documento_cliente="20000000001",
    nombre_tipo_documento="CUIT",
)

IVAS = [{"alic_iva": "21.00", "importe": "17.36"}]
PAGOS = [{"ds": "Efectivo", "importe": "100.00"}]


@pytest.fixture(autouse=True)
def qr_como_texto(monkeypatch):
    """El raster del QR depende de la libreria de imagenes, no del formato."""

    def _fake_qr(self, content, *args, **kwargs):
        self.text(content)

    monkeypatch.setattr(Dummy, "qr", _fake_qr, raising=True)


def _item(qty, ds="Queso cremoso", importe=800.0):
    return {"alic_iva": 21.0, "importe": importe, "ds": ds, "qty": qty}


def _render_factura(items, encabezado=None, columns=None):
    printer = Dummy()
    comandos = EscPComandos(printer, columns=columns)
    with EscposIO(printer, autocut=False, autoclose=False) as escpos:
        ok = comandos.printFacturaElectronica(
            escpos,
            encabezado=dict(encabezado or ENCABEZADO_FACTURA_B),
            items=items,
            ivas=IVAS,
            pagos=PAGOS,
        )
    assert ok is True
    return printer.output.decode("latin-1")


def _render_remito(items, columns=None):
    printer = Dummy()
    comandos = EscPComandos(printer, columns=columns)
    with EscposIO(printer, autocut=False, autoclose=False) as escpos:
        ok = comandos.printRemito(
            escpos,
            encabezado={"nombre_cliente": "Cliente de Prueba"},
            items=items,
            pagos=[],
        )
    assert ok is True
    return printer.output.decode("latin-1")


def _render_pedido(items):
    printer = Dummy()
    comandos = EscPComandos(printer)
    with EscposIO(printer, autocut=False, autoclose=False) as escpos:
        ok = comandos.printPedido(
            escpos,
            encabezado={"nombre_proveedor": "Proveedor de Prueba"},
            items=items,
        )
    assert ok is True
    return printer.output.decode("latin-1")


def _linea_con(salida, texto):
    """La unica linea impresa que contiene `texto`, sin los comandos ESC/POS de formato."""
    sin_comandos = re.sub(r"\x1b[!MaE\-t][\x00-\xff]", "", salida)
    lineas = [l for l in sin_comandos.split("\n") if texto in l]
    assert len(lineas) == 1, (texto, lineas)
    return lineas[0]


# ---------------------------------------------------------------------------
# la funcion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        (0.125, "0.125"),
        (2.0, "2"),
        (2, "2"),
        (1.5, "1.5"),
        (3.3751, "3.3751"),
        (0.0001, "0.0001"),
        (10, "10"),
        (100.0, "100"),
        (0, "0"),
        ("0.125", "0.125"),  # el servidor puede mandar decimales como string
        ("3.3751", "3.3751"),
        (3.37514, "3.3751"),  # mas de 4 decimales: se redondea al cuarto
        (0.00001, "0"),  # redondea a cero: nunca "0.0000" ni "-0"
        (-0.00001, "0"),
        (-1.25, "-1.25"),
    ],
)
def test_cantidad_a_string(entrada, esperado):
    assert cantidadToString(entrada) == esperado


def test_importes_siguen_con_dos_decimales():
    # floatToString es para importes: no cambia
    assert floatToString(0.126) == "0.13"
    assert floatToString(3.3751) == "3.38"
    assert floatToString(2.0) == "2"
    assert floatToString(1.5) == "1.5"


# ---------------------------------------------------------------------------
# factura electronica
# ---------------------------------------------------------------------------


def test_factura_a_cantidad_de_3_decimales_exacta():
    salida = _render_factura([_item(0.125)], encabezado=ENCABEZADO_FACTURA_A)

    assert "0.125 x 800 (21)" in salida
    assert "0.13 x" not in salida


def test_factura_a_cantidad_de_4_decimales_exacta():
    salida = _render_factura([_item(3.3751)], encabezado=ENCABEZADO_FACTURA_A)

    assert "3.3751 x 800 (21)" in salida


def test_factura_b_80mm_cantidad_de_3_decimales_exacta_y_alineada():
    salida = _render_factura([_item(0.125)])

    # importe: 0.125 x 800 = 100.00 (los totales siguen a 2 decimales)
    linea = _linea_con(salida, "0.125 ")
    assert linea.startswith("0.125 Queso cremoso")
    assert linea.endswith("100.00")
    assert len(linea) == 40  # el PRECIO sigue alineado al borde derecho


def test_factura_b_80mm_cantidad_de_4_decimales_no_se_pega_a_la_descripcion():
    salida = _render_factura([_item(3.3751)])

    linea = _linea_con(salida, "3.3751")
    assert linea.startswith("3.3751 Queso")  # una columna de separacion
    assert len(linea) == 40
    assert linea.endswith("2,700.08")  # round(3.3751 x 800, 2)


def test_factura_b_58mm_cantidad_no_se_trunca():
    # en 58mm la columna CANT mide 4: "0.125" (5) antes salia truncada a "0.12"
    salida = _render_factura([_item(0.125)], columns=32)

    linea = _linea_con(salida, "0.125 ")
    assert linea.startswith("0.125 Queso")
    assert len(linea) == 32


def test_factura_b_cantidad_entera_no_cambia_el_layout():
    # caso de siempre: cantidad entera => la columna CANT mide lo mismo que antes
    salida = _render_factura([_item(2, importe=50.0)])

    linea = _linea_con(salida, "2 ")
    assert linea.startswith("2" + " " * 5 + "Queso cremoso")
    assert len(linea) == 40


def test_factura_b_descripcion_larga_se_acorta_para_no_correr_el_precio():
    salida = _render_factura([_item(3.3751, ds="Queso cremoso por kilo fraccionado")])

    linea = _linea_con(salida, "3.3751")
    assert len(linea) == 40
    assert linea.endswith("2,700.08")


# ---------------------------------------------------------------------------
# remito
# ---------------------------------------------------------------------------


def test_remito_cantidad_de_3_decimales_exacta_y_alineada():
    salida = _render_remito([_item(0.125)])

    linea = _linea_con(salida, "0.125 ")
    assert linea.startswith("0.125 Queso cremoso")
    assert linea.endswith("100.00")
    assert len(linea) == 40
    assert "0.13" not in salida


def test_remito_cantidad_de_4_decimales_exacta():
    salida = _render_remito([_item(3.3751)])

    linea = _linea_con(salida, "3.3751")
    assert linea.startswith("3.3751 Queso")
    assert len(linea) == 40
    assert linea.endswith("2,700.08")


def test_remito_58mm_cantidad_no_se_trunca():
    salida = _render_remito([_item(0.125)], columns=32)

    linea = _linea_con(salida, "0.125 ")
    assert linea.startswith("0.125 Queso")
    assert len(linea) == 32


def test_remito_cantidad_sin_decimales_se_imprime_sin_ceros():
    salida = _render_remito([_item(2.0, importe=50.0), _item(1.5, ds="Pan", importe=10.0)])

    assert "2.00" not in salida
    assert _linea_con(salida, "Queso").startswith("2" + " " * 5 + "Queso")
    assert _linea_con(salida, "Pan").startswith("1.5" + " " * 3 + "Pan")


# ---------------------------------------------------------------------------
# pedido / orden de compra
# ---------------------------------------------------------------------------


def test_pedido_cantidad_de_3_decimales_exacta():
    item = {"ds": "Harina", "qty": 0.125, "unidad_de_medida": "kg"}
    salida = _render_pedido([item])

    assert "0.125 kg\t" in salida
    assert "0.13" not in salida


def test_pedido_cantidad_de_4_decimales_exacta():
    item = {"ds": "Harina", "qty": "3.3751", "unidad_de_medida": "kg"}
    salida = _render_pedido([item])

    assert "3.3751 kg\t" in salida
