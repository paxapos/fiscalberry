"""
El arqueo de caja impreso tiene que decir a qué arqueo pertenece (arqueo_id).
Si el backend no lo manda (versiones viejas), se imprime igual que antes.
"""

import pytest
from escpos.escpos import EscposIO
from escpos.printer import Dummy

from fiscalberry.common.EscPComandos import EscPComandos


def _encabezado(**extra):
    enc = {
        "nombreComercio": "Paxapoga",
        "fechaDesde": "01-10-2026 08:00",
        "fechaHasta": "01-10-2026 20:00",
        "ArqueoDateTime": "2026-10-01 20:05:00",
        "nombreCaja": "Caja 1",
        "aliasUsuario": "admin",
        "observacion": "",
        "importeInicial": "1000",
        "importeFinal": "1000",
        "diferencia": "0",
    }
    enc.update(extra)
    return enc


def _imprimir(**kwargs):
    printer = Dummy()
    comandos = EscPComandos(printer)
    with EscposIO(printer, autocut=False, autoclose=False) as escpos:
        comandos.printArqueo(escpos, **kwargs)
    return printer.output.decode("latin-1", errors="replace")


@pytest.mark.parametrize("kwargs", [
    {"encabezado": _encabezado(arqueo_id=4321)},
    {"encabezado": _encabezado(), "arqueo_id": "4321"},
])
def test_imprime_el_id_del_arqueo(kwargs):
    salida = _imprimir(**kwargs)

    assert "'Arqueo ID': 4321" in salida
    # Va en el encabezado, antes de la fecha de cierre.
    assert salida.index("'Arqueo ID'") < salida.index("'Fecha de Cierre'")


def test_sin_arqueo_id_no_imprime_la_linea():
    salida = _imprimir(encabezado=_encabezado())

    assert "Arqueo ID" not in salida
    assert "'Fecha de Cierre'" in salida
