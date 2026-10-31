"""
Los goldens de tests/golden/ son los bytes exactos que EscPComandos manda hoy a
la impresora. Paxapos los usa para probar que su render server-side sale igual
(épica paxapos/paxapos#1723). Si este test falla, EscPComandos cambió un byte:
o es un bug, o es un cambio de formato a propósito y hay que regenerar con
`python tools/golden_escpos.py` (y hacer el mismo cambio en Paxapos).
"""

import importlib.util
import os

import pytest

_TOOL = os.path.join(os.path.dirname(__file__), "..", "tools", "golden_escpos.py")


def _tool():
    spec = importlib.util.spec_from_file_location("golden_escpos", _TOOL)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_hay_un_golden_por_payload_y_ancho():
    tool = _tool()
    nombres = tool.payload_names()
    assert len(nombres) >= 20
    for nombre in nombres:
        for cols in tool.COLUMNS:
            assert os.path.exists(os.path.join(tool.BYTES_DIR, f"{nombre}.{cols}.bin")), (nombre, cols)


def test_escpcomandos_imprime_lo_mismo_que_los_goldens():
    tool = _tool()
    distintas = tool.version_mismatch()
    if distintas:
        pytest.skip(f"versiones distintas a las de los goldens (requirements.dev.txt): {distintas}")
    assert tool.check(tool.build()) == []


def test_la_hora_queda_congelada_en_los_comprobantes_con_fecha():
    tool = _tool()
    salida = tool.render(tool.load_payload("remito_completo"), 40)
    assert b"Fecha: 10/07/2026 21:45" in salida
