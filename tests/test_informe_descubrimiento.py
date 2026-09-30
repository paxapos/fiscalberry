# coding=utf-8
"""
Informe de descubrimiento (--discovery-report) y empaquetado del asistente.

El informe lo corre la prueba del instalador en un Windows real: acá se
comprueba que una sección rota no tapa a las demás y que el código de salida
lo refleja. El empaquetado: todo módulo del asistente que el selftest importa
tiene que estar en los hiddenimports del .spec, o el exe instalado falla y
el selftest del updater no lo detecta.
"""

import ast
import json
import os

import pytest

from fiscalberry.common import discovery_report

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_una_seccion_rota_no_tapa_a_las_demas(tmp_path):
    def rota():
        raise OSError(5, "Acceso denegado")

    ruta = tmp_path / "informe.json"
    codigo = discovery_report.run(str(ruta), sections={"bien": lambda: [1, 2], "mal": rota})
    informe = json.loads(ruta.read_text(encoding="utf-8"))

    assert codigo == 1
    assert informe["bien"] == [1, 2]
    assert "Acceso denegado" in informe["mal"]["error"]
    assert informe["fallas"] == ["mal"]


def test_informe_completo_en_esta_plataforma(tmp_path):
    ruta = tmp_path / "informe.json"
    codigo = discovery_report.run(str(ruta))
    informe = json.loads(ruta.read_text(encoding="utf-8"))
    assert codigo == 0, informe["fallas"]
    assert set(discovery_report.SECTIONS) <= set(informe)
    assert isinstance(informe["adaptadores"], list)


def test_el_arranque_temprano_atiende_el_informe(tmp_path):
    from fiscalberry.common.updater import cli_modes

    ruta = tmp_path / "informe.json"
    with pytest.raises(SystemExit) as salida:
        cli_modes.handle_early_modes(["fiscalberry-gui.exe", "--discovery-report",
                                      "--report", str(ruta)])
    assert salida.value.code == 0
    assert "--discovery-report" in cli_modes.MODES
    assert json.loads(ruta.read_text(encoding="utf-8"))["fallas"] == []


def _hiddenimports():
    arbol = ast.parse(open(os.path.join(RAIZ, "fiscalberry-gui.spec"), encoding="utf-8").read())
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.keyword) and nodo.arg == "hiddenimports":
            return {e.value for e in nodo.value.elts}
    raise AssertionError("fiscalberry-gui.spec no tiene hiddenimports")


def _imports_del_selftest_de_la_gui():
    fuente = open(os.path.join(RAIZ, "src", "fiscalberry", "common", "updater", "cli_modes.py"),
                  encoding="utf-8").read()
    arbol = ast.parse(fuente)
    gui = next(n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name == "_gui")
    return {alias.name for n in ast.walk(gui) if isinstance(n, ast.Import) for alias in n.names}


def test_los_modulos_del_asistente_se_empaquetan_y_el_selftest_los_prueba():
    ocultos = _hiddenimports()
    selftest = _imports_del_selftest_de_la_gui()
    asistente = {m for m in selftest if m.startswith("fiscalberry.")
                 and m not in ("fiscalberry.ui.fiscalberry_app",)}
    faltan = sorted(asistente - ocultos)
    assert not faltan, f"Faltan en hiddenimports de fiscalberry-gui.spec: {faltan}"

    # Y al revés: lo que el .spec empaqueta del asistente lo prueba el selftest.
    del_asistente = {m for m in ocultos if m.startswith(("fiscalberry.common.printer",
                                                         "fiscalberry.common.network",
                                                         "fiscalberry.common.usb",
                                                         "fiscalberry.common.windows_queues",
                                                         "fiscalberry.common.discovery",
                                                         "fiscalberry.common.support"))}
    assert del_asistente <= selftest, sorted(del_asistente - selftest)
