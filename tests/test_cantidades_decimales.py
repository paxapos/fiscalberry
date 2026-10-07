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
    PRECIO queda alineado (papel de 80mm y de 58mm);
  * el total de linea (PRECIO/IMPORTE) tampoco se trunca: si no entra, la
    columna se ensancha a costa de la descripcion (issue #198), y si todo entra
    la linea sale igual que siempre;
  * subtotal, descuento, IVA, pagos y transparencia fiscal tampoco se truncan:
    el importe se ensancha a costa de la etiqueta (issue #198);
  * el pedido alinea la descripcion con espacios, no con tabuladores.
"""

import re

import pytest
from escpos.escpos import EscposIO
from escpos.printer import Dummy

from fiscalberry.common.EscPComandos import EscPComandos, cantidadToString, floatToString, pad


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


def _render_factura(items, encabezado=None, columns=None, **extra):
    printer = Dummy()
    comandos = EscPComandos(printer, columns=columns)
    kwargs = dict(
        encabezado=dict(encabezado or ENCABEZADO_FACTURA_B),
        items=items,
        ivas=IVAS,
        pagos=PAGOS,
    )
    kwargs.update(extra)  # ivas, pagos, addAdditional, otros_impuestos
    with EscposIO(printer, autocut=False, autoclose=False) as escpos:
        ok = comandos.printFacturaElectronica(escpos, **kwargs)
    assert ok is True
    return printer.output.decode("latin-1")


def _render_remito(items, columns=None, **extra):
    printer = Dummy()
    comandos = EscPComandos(printer, columns=columns)
    kwargs = dict(
        encabezado={"nombre_cliente": "Cliente de Prueba"},
        items=items,
        pagos=[],
    )
    kwargs.update(extra)  # pagos, addAdditional
    with EscposIO(printer, autocut=False, autoclose=False) as escpos:
        ok = comandos.printRemito(escpos, **kwargs)
    assert ok is True
    return printer.output.decode("latin-1")


def _render_pedido(items, columns=None):
    printer = Dummy()
    comandos = EscPComandos(printer, columns=columns)
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
# cantidad corta pero que ya no entra con separacion (caso comun: 1.25 en 58mm)
# ---------------------------------------------------------------------------


def test_factura_b_58mm_cantidad_de_2_decimales_1_25_no_se_pega():
    # "1.25" mide 4 = cant_cols en 58mm: antes quedaba pegada a la descripcion
    salida = _render_factura([_item(1.25, importe=100.0)], columns=32)

    linea = _linea_con(salida, "1.25")
    assert linea.startswith("1.25 Queso cremoso")
    assert linea.endswith("125.00")
    assert len(linea) == 32


def test_remito_58mm_cantidad_de_2_decimales_1_25_no_se_pega():
    salida = _render_remito([_item(1.25, importe=100.0)], columns=32)

    linea = _linea_con(salida, "1.25")
    assert linea.startswith("1.25 Queso cremoso")
    assert linea.endswith("125.00")
    assert len(linea) == 32


# ---------------------------------------------------------------------------
# total de linea (issue #198): no se trunca nunca
# ---------------------------------------------------------------------------


def _legacy(comandos, cant, ds, total):
    """La linea de item tal como se armaba antes: tres pad() sin ensanchar nada."""
    return (
        pad(cant, comandos.cant_cols, " ", "l")
        + pad(ds[0 : comandos.desc_cols - 2], comandos.desc_cols, " ", "l")
        + pad(total, comandos.price_cols, " ", "r")
    )


@pytest.mark.parametrize("columns", [None, 32])
@pytest.mark.parametrize("render", [_render_factura, _render_remito])
@pytest.mark.parametrize(
    "qty, importe, total",
    [
        (1, 50.0, "50.00"),
        (2, 12.5, "25.00"),
        (3, 99.99, "299.97"),
        (10, 1000.0, "10,000.00"),
        (1, 9999.99, "9,999.99"),
    ],
)
def test_si_todo_entra_la_linea_es_la_de_siempre(columns, render, qty, importe, total):
    comandos = EscPComandos(Dummy(), columns=columns)
    ds = "Queso cremoso"

    salida = render([_item(qty, ds=ds, importe=importe)], columns=columns)

    esperada = _legacy(comandos, str(qty), ds, total)
    assert _linea_con(salida, ds) == esperada


@pytest.mark.parametrize("render", [_render_factura, _render_remito])
def test_total_largo_en_58mm_no_se_trunca_y_el_precio_queda_alineado(render):
    # 9,876,543.12 mide 12 y la columna PRECIO de 58mm mide 10: antes salia "9,876,543."
    salida = render([_item(1, importe=9876543.12)], columns=32)

    linea = _linea_con(salida, "Queso")
    assert linea.endswith("9,876,543.12")
    assert linea.startswith("1   Queso")
    assert len(linea) == 32


@pytest.mark.parametrize("render", [_render_factura, _render_remito])
def test_total_largo_en_80mm_no_se_trunca_y_el_precio_queda_alineado(render):
    # 98,765,432.10 mide 13 y la columna PRECIO de 80mm mide 12
    salida = render([_item(1, importe=98765432.10)])

    linea = _linea_con(salida, "Queso")
    assert linea.endswith("98,765,432.10")
    assert linea.startswith("1     Queso")
    assert len(linea) == 40


@pytest.mark.parametrize("render", [_render_factura, _render_remito])
@pytest.mark.parametrize("columns, ancho", [(None, 40), (32, 32)])
def test_cantidad_larga_y_total_largo_a_la_vez(render, columns, ancho):
    # las dos columnas se ensanchan a costa de la descripcion; la linea mide lo mismo
    salida = render([_item(3.3751, importe=9000000.0)], columns=columns)

    linea = _linea_con(salida, "3.3751")
    assert linea.startswith("3.3751 ")
    assert linea.endswith("30,375,900.00")  # round(3.3751 x 9000000, 2)
    assert len(linea) == ancho


@pytest.mark.parametrize("columns, ancho", [(None, 40), (32, 32)])
def test_descripcion_larga_con_total_largo_se_acorta_y_deja_aire_antes_del_precio(columns, ancho):
    salida = _render_remito(
        [_item(1, ds="Queso cremoso por kilo fraccionado", importe=98765432.10)], columns=columns
    )

    linea = _linea_con(salida, "Queso")
    assert len(linea) == ancho
    assert linea[: -len("98,765,432.10")].endswith("  ")  # dos espacios de margen, como siempre


@pytest.mark.parametrize("columns, ancho", [(None, 40), (32, 32)])
def test_factura_a_total_largo_no_se_trunca(columns, ancho):
    # formato de factura A: "cant x precio (IVA)" arriba y "descripcion ... importe" abajo
    salida = _render_factura(
        [_item(1, importe=98765432.10)], encabezado=ENCABEZADO_FACTURA_A, columns=columns
    )

    linea = _linea_con(salida, "Queso")
    assert linea.startswith("Queso cremoso")
    assert linea.endswith("98,765,432.10")
    assert len(linea) == ancho


def test_factura_a_total_que_entra_no_cambia():
    salida = _render_factura([_item(1, importe=100.0)], encabezado=ENCABEZADO_FACTURA_A)

    linea = _linea_con(salida, "Queso cremoso")
    assert linea == "Queso cremoso" + " " * (40 - len("Queso cremoso") - len("100.00")) + "100.00"


# ---------------------------------------------------------------------------
# subtotal, descuento, IVA, pagos y transparencia fiscal (issue #198)
# ---------------------------------------------------------------------------

# 16 caracteres: no entra ni en la columna de 58mm (10) ni en la de 80mm (12)
IMPORTE_LARGO = 9876543210.12
IMPORTE_LARGO_TXT = "9,876,543,210.12"
# 12 caracteres: entra en 80mm, no en 58mm
IMPORTE_MEDIO = 1234567.89
IMPORTE_MEDIO_TXT = "1,234,567.89"

# (columns, ancho del papel, price_cols)
PAPELES = [(32, 32, 10), (None, 40, 12)]


def _enc_inscripto(total, neto, iva):
    return dict(
        ENCABEZADO_FACTURA_A,
        importe_total=f"{total:.2f}",
        importe_neto=f"{neto:.2f}",
        importe_iva=f"{iva:.2f}",
    )


def _linea_importe_ok(linea, etiqueta, importe, ancho):
    """El importe aparece completo al final, precedido por el signo, y la linea mide el papel."""
    assert len(linea) == ancho, linea
    assert re.search(r"\$ *" + re.escape(importe) + r"$", linea), linea
    assert linea.startswith(etiqueta), linea


@pytest.mark.parametrize("columns, ancho, price_cols", PAPELES)
def test_factura_a_subtotal_neto_e_iva_largos_no_se_truncan(columns, ancho, price_cols):
    salida = _render_factura(
        [_item(1, importe=100.0)],
        encabezado=_enc_inscripto(IMPORTE_LARGO, 8161854471.17, 1714688738.95),
        ivas=[{"alic_iva": "21.00", "importe": "1714688738.95"}],
        columns=columns,
    )

    _linea_importe_ok(_linea_con(salida, "SUBTOTAL:"), "SUBTOTAL:", IMPORTE_LARGO_TXT, ancho)
    _linea_importe_ok(
        _linea_con(salida, "Neto sin IVA:"), "Neto sin IVA:", "8,161,854,471.17", ancho
    )
    _linea_importe_ok(_linea_con(salida, "IVA 21.00:"), "IVA 21.00:", "1,714,688,738.95", ancho)


@pytest.mark.parametrize("columns, ancho, price_cols", PAPELES)
def test_factura_descuento_y_subtotal_largos_no_se_truncan(columns, ancho, price_cols):
    salida = _render_factura(
        [_item(1, importe=100.0)],
        encabezado=dict(ENCABEZADO_FACTURA_B, importe_total="9876543210.12"),
        addAdditional={
            "amount": "1234567890.12",
            "description": "Descuento",
            "descuento_porcentaje": "10",
        },
        columns=columns,
    )

    # subtotal = total + descuento (11.111.111.100,24); el descuento viaja en negativo
    _linea_importe_ok(_linea_con(salida, "SUBTOTAL:"), "SUBTOTAL:", "11,111,111,100.24", ancho)
    _linea_importe_ok(_linea_con(salida, "Descuento"), "Descuento", "-1,234,567,890.12", ancho)


@pytest.mark.parametrize("columns, ancho, price_cols", PAPELES)
def test_remito_subtotal_y_descuento_largos_no_se_truncan(columns, ancho, price_cols):
    salida = _render_remito(
        [_item(1, importe=IMPORTE_LARGO)],
        columns=columns,
        addAdditional={"amount": 1234567890.12, "description": "Descuento"},
    )

    _linea_importe_ok(_linea_con(salida, "SUBTOTAL:"), "SUBTOTAL:", IMPORTE_LARGO_TXT, ancho)
    _linea_importe_ok(_linea_con(salida, "Descuento"), "Descuento", "-1,234,567,890.12", ancho)


@pytest.mark.parametrize("columns, ancho, price_cols", PAPELES)
def test_remito_pago_largo_no_se_trunca(columns, ancho, price_cols):
    salida = _render_remito(
        [_item(1, importe=100.0)],
        columns=columns,
        pagos=[{"ds": "Efectivo", "importe": "9876543210.12"}],
    )

    _linea_importe_ok(_linea_con(salida, "Efectivo"), "Efectivo", IMPORTE_LARGO_TXT, ancho)


@pytest.mark.parametrize("columns, ancho, price_cols", PAPELES)
def test_factura_pagos_detallados_largos_no_se_truncan(columns, ancho, price_cols):
    # formato de factura B: "Recibimos:" con cada pago, la suma y el vuelto (sin signo $)
    salida = _render_factura(
        [_item(1, importe=100.0)],
        columns=columns,
        pagos=[
            {"ds": "Efectivo", "importe": "9876543210.12"},
            {"ds": "Tarjeta", "importe": "1000.00"},
            {"ds": "Vuelto", "importe": "-500.00"},
        ],
    )

    def sin_signo(inicio, importe):
        # sin signo $; la etiqueta larga se acorta para dejar lugar al importe
        linea = _linea_con(salida, inicio)
        assert len(linea) == ancho, linea
        assert linea.startswith(inicio), linea
        assert linea.endswith(importe), linea

    sin_signo("EFECTIVO", IMPORTE_LARGO_TXT)
    sin_signo("La suma de", "9,876,544,210.12")
    sin_signo("Su vuelto", "500.00")


@pytest.mark.parametrize("columns, ancho, price_cols", PAPELES)
def test_factura_transparencia_fiscal_importes_largos_no_se_truncan(columns, ancho, price_cols):
    salida = _render_factura(
        [_item(1, importe=100.0)],
        encabezado=dict(ENCABEZADO_FACTURA_B, importe_iva="1714688738.95"),
        ivas=[{"alic_iva": "21.00", "importe": "1714688738.95"}],
        otros_impuestos=1234567890.12,
        columns=columns,
    )

    _linea_importe_ok(
        _linea_con(salida, "IVA Contenido:"), "IVA Contenido:", "1,714,688,738.95", ancho
    )
    # la etiqueta larga se acorta para dejar lugar al importe; el importe no
    _linea_importe_ok(_linea_con(salida, "Otros Imp."), "Otros Imp.", "1,234,567,890.12", ancho)


def test_importe_medio_entra_en_80mm_y_se_ensancha_en_58mm():
    # 1,234,567.89 (12): justo la columna de 80mm, no la de 58mm (10)
    ancho80 = _linea_con(
        _render_remito([_item(1, importe=100.0)], addAdditional={"amount": 10, "description": "Descuento"}),
        "SUBTOTAL:",
    )
    assert len(ancho80) == 40

    salida58 = _render_remito(
        [_item(1, importe=IMPORTE_MEDIO)],
        columns=32,
        addAdditional={"amount": 10, "description": "Descuento"},
    )
    _linea_importe_ok(_linea_con(salida58, "SUBTOTAL:"), "SUBTOTAL:", IMPORTE_MEDIO_TXT, 32)

    salida80 = _render_remito(
        [_item(1, importe=IMPORTE_MEDIO)],
        addAdditional={"amount": 10, "description": "Descuento"},
    )
    _linea_importe_ok(_linea_con(salida80, "SUBTOTAL:"), "SUBTOTAL:", IMPORTE_MEDIO_TXT, 40)


def _legacy_importe(comandos, etiqueta, importe, signo="$"):
    """La linea tal como se armaba antes: dos pad() sin ensanchar nada."""
    ancho_etiqueta = comandos.desc_cols_ext - (1 if signo else 0)
    return (
        pad(etiqueta, ancho_etiqueta, " ", "l")
        + signo
        + pad(importe, comandos.price_cols, " ", "r")
    )


@pytest.mark.parametrize("columns", [None, 32])
def test_si_los_importes_entran_las_lineas_son_las_de_siempre(columns):
    comandos = EscPComandos(Dummy(), columns=columns)

    # factura A: subtotal, neto sin IVA e IVA
    salida = _render_factura(
        [_item(1, importe=100.0)],
        encabezado=_enc_inscripto(1234.56, 1020.30, 214.26),
        ivas=[{"alic_iva": "21.00", "importe": "214.26"}],
        columns=columns,
    )
    assert _linea_con(salida, "SUBTOTAL:") == _legacy_importe(comandos, "SUBTOTAL:", "1,234.56")
    assert _linea_con(salida, "Neto sin IVA:") == _legacy_importe(
        comandos, "Neto sin IVA:", "1,020.30"
    )
    assert _linea_con(salida, "IVA 21.00:") == _legacy_importe(comandos, "IVA 21.00:", "214.26")

    # factura B con descuento y pagos detallados; remito con descuento y pago simple
    salida = _render_factura(
        [_item(1, importe=100.0)],
        encabezado=dict(ENCABEZADO_FACTURA_B, importe_total="100.00"),
        addAdditional={"amount": "10.00", "description": "Descuento", "descuento_porcentaje": "10"},
        pagos=[{"ds": "Efectivo", "importe": "150.00"}, {"ds": "Vuelto", "importe": "-50.00"}],
        columns=columns,
    )
    assert _linea_con(salida, "SUBTOTAL:") == _legacy_importe(comandos, "SUBTOTAL:", "110.00")
    assert _linea_con(salida, "Descuento") == _legacy_importe(comandos, "Descuento", "-10.00")
    assert _linea_con(salida, "EFECTIVO") == _legacy_importe(comandos, "EFECTIVO", "150.00", signo="")
    assert _linea_con(salida, "Su vuelto:") == _legacy_importe(comandos, "Su vuelto:", "50.00", signo="")

    salida = _render_remito(
        [_item(1, importe=100.0)],
        columns=columns,
        addAdditional={"amount": 10, "description": "Descuento"},
        pagos=[{"ds": "Efectivo", "importe": "100.00"}],
    )
    assert _linea_con(salida, "SUBTOTAL:") == _legacy_importe(comandos, "SUBTOTAL:", "100.00")
    assert _linea_con(salida, "Descuento") == _legacy_importe(comandos, "Descuento", "-10.00")
    assert _linea_con(salida, "Efectivo") == _legacy_importe(comandos, "Efectivo", "100.00")


# ---------------------------------------------------------------------------
# pedido / orden de compra
# ---------------------------------------------------------------------------


def _columna_de(linea, texto):
    return linea.index(texto)


def test_pedido_cantidad_de_3_decimales_exacta():
    item = {"ds": "Harina", "qty": 0.125, "unidad_de_medida": "kg"}
    salida = _render_pedido([item])

    assert "0.125 kg " in salida
    assert "0.13" not in salida


def test_pedido_cantidad_de_4_decimales_exacta():
    item = {"ds": "Harina", "qty": "3.3751", "unidad_de_medida": "kg"}
    salida = _render_pedido([item])

    assert "3.3751 kg " in salida


@pytest.mark.parametrize("columns", [None, 32])
def test_pedido_alinea_la_descripcion_con_cantidades_de_hasta_4_decimales(columns):
    items = [
        {"ds": "Harina", "qty": 2, "unidad_de_medida": "kg"},
        {"ds": "Azucar", "qty": 0.125, "unidad_de_medida": "kg"},
        {"ds": "Manteca", "qty": 3.3751, "unidad_de_medida": "kg"},
        {"ds": "Leche", "qty": 12.5, "unidad_de_medida": "lt"},
    ]
    salida = _render_pedido(items, columns=columns)

    assert "\t" not in salida  # espacios, no tab stops
    sin_comandos = re.sub(r"\x1b[!MaE\-t][\x00-\xff]", "", salida)
    lineas = sin_comandos.split("\n")
    columnas = {
        _columna_de(_linea_con(salida, ds), ds) for ds in ("Harina", "Azucar", "Manteca", "Leche")
    }
    cabecera = [l for l in lineas if l.startswith("CANT")][0]

    assert len(columnas) == 1  # todas las descripciones empiezan en la misma columna
    assert _columna_de(cabecera, "DESCRIPCI") in columnas  # y debajo de su encabezado
    assert max(len(l) for l in lineas if "kg" in l or " lt" in l) <= (columns or 40)


def test_pedido_con_cantidades_cortas_mantiene_la_columna_de_siempre():
    # "2 kg" entra en los 8 de siempre: la descripcion queda en la columna 8
    salida = _render_pedido([{"ds": "Harina", "qty": 2, "unidad_de_medida": "kg"}])

    assert _columna_de(_linea_con(salida, "Harina"), "Harina") == 8
