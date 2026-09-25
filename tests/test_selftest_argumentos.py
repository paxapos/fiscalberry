# coding=utf-8
"""
El selftest de la GUI no puede morir por los argumentos con que se lo llama.

Kivy parsea sys.argv al importarse y, ante una opción que no conoce, hace
sys.exit(2). `fiscalberry-gui.exe --selftest --report x` le pasaba justamente
eso: el proceso moría con código 2 sin escribir el reporte. El updater no lo
veía porque lanza el selftest con KIVY_NO_ARGS=1, pero corrido a mano (soporte)
o desde la CI del instalador fallaba siempre.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# Sin importar Kivy acá: al importarse bajo pytest setea KIVY_UNITTEST=1 en el
# entorno, el subproceso lo heredaría y Kivy dejaría de parsear argumentos
# (el test pasaría aunque el bug siguiera).
pytestmark = pytest.mark.skipif(importlib.util.find_spec("kivy") is None,
                                reason="sin Kivy")

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def carpeta():
    """
    Temporal propio y no tmp_path: Kivy también deja de parsear argumentos si
    alguno contiene la palabra "pytest", y la ruta de tmp_path la contiene.
    """
    ruta = tempfile.mkdtemp(prefix="fb-selftest-args-")
    yield Path(ruta)
    shutil.rmtree(ruta, ignore_errors=True)


def test_el_selftest_de_la_gui_ignora_sus_propios_argumentos(carpeta):
    reporte = carpeta / "reporte.txt"
    assert "pytest" not in str(reporte)
    codigo = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {SRC!r})
        sys.argv = ["fiscalberry-gui.exe", "--selftest", "--report", {str(reporte)!r}]
        from fiscalberry.common.updater import cli_modes, install_kind
        install_kind.is_gui = lambda: True
        sys.exit(cli_modes.run_selftest(ruta_reporte={str(reporte)!r}))
    """)
    # Como lo corre una persona o la CI: sin nada que apague el parseo de
    # argumentos de Kivy.
    apagan_el_parseo = ("KIVY_NO_ARGS", "KIVY_UNITTEST", "KIVY_PACKAGING")
    entorno = {k: v for k, v in os.environ.items() if k not in apagan_el_parseo}
    entorno["XDG_CONFIG_HOME"] = str(carpeta / "config")
    entorno["XDG_DATA_HOME"] = str(carpeta / "data")

    proc = subprocess.run([sys.executable, "-c", codigo], capture_output=True,
                          text=True, timeout=180, env=entorno)

    assert reporte.exists(), (
        f"el selftest no escribió el reporte (código {proc.returncode}): "
        f"{proc.stdout[-500:]} {proc.stderr[-500:]}")
    contenido = reporte.read_text(encoding="utf-8")
    assert "SystemExit" not in contenido, contenido
