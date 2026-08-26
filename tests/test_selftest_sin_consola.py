# coding=utf-8
"""
El selftest previo a instalar una actualización, cuando el binario no tiene
consola.

El updater corre el binario NUEVO con `--selftest` y solo instala si encuentra
una marca de éxito. Esa marca viajaba por stdout, pero el .exe de la GUI se
compila con `console=False` y ahí no hay stdout: la marca no llegaba nunca y
**ninguna** actualización de la GUI en Windows podía instalarse. Ahora el padre
le pasa además un archivo (`--report`) donde dejar el veredicto.

La regla que ordena todo este archivo es que ante la duda NO se instala. Un
canal de comunicación nuevo entre dos procesos es exactamente el lugar donde se
cuela un "no pude leer nada, debe estar bien": la mayoría de los tests de acá
existen para prohibir eso, caso por caso.
"""

import os

import pytest

from soporte_consola import GUI_SIN_STDOUT, binario_falso

from fiscalberry.common.updater import selftest
from fiscalberry.common.updater.cli_modes import _publicar_resultado


VERSION = "9.9.9"
MARCA = selftest.selftest_report(VERSION)


# --------------------------------------------------------------------------
# Los binarios de mentira que se le dan a probar al updater
# --------------------------------------------------------------------------

@pytest.fixture
def gui_windowed(tmp_path):
    """Como el .exe de la GUI: responde bien, pero su stdout no va a ningún lado."""
    return binario_falso(tmp_path, "gui-ok", f"""
{GUI_SIN_STDOUT}
from fiscalberry.common.updater.cli_modes import _arg, _publicar_resultado
_publicar_resultado([{MARCA!r}], _arg(sys.argv, "--report"))
sys.exit(0)
""")


@pytest.fixture
def binario_anterior(tmp_path):
    """De una versión previa: tiene consola y no conoce `--report`."""
    return binario_falso(tmp_path, "anterior", f"""
print({MARCA!r})
sys.exit(0)
""")


@pytest.fixture
def mudo(tmp_path):
    """Sin stdout y sin escribir el reporte: sale 0 pero no dice nada."""
    return binario_falso(tmp_path, "mudo", f"""
{GUI_SIN_STDOUT}
sys.exit(0)
""")


@pytest.fixture
def roto(tmp_path):
    """Falla el selftest como fallaría de verdad: imports que no están."""
    return binario_falso(tmp_path, "roto", f"""
{GUI_SIN_STDOUT}
from fiscalberry.common.updater.cli_modes import _arg, _publicar_resultado
_publicar_resultado(
    ["SELFTEST FALLO -> imports del núcleo: ModuleNotFoundError: No module named 'escpos'"],
    _arg(sys.argv, "--report"))
sys.exit(1)
""")


# --------------------------------------------------------------------------
# Lo que sí tiene que pasar
# --------------------------------------------------------------------------

def test_un_binario_sin_stdout_puede_pasar_el_selftest(gui_windowed):
    """El bug de fondo: la GUI de Windows no podía actualizarse nunca."""
    ok, detalle = selftest.run(gui_windowed, expected_version=VERSION)

    assert ok, detalle
    # La marca queda al final: los mensajes de error recortan por ahí
    # (`salida[-400:]`), y es el veredicto lo que tiene que sobrevivir al corte,
    # no el ruido de arranque del binario.
    assert detalle.rstrip().endswith(MARCA), detalle


def test_un_binario_anterior_se_sigue_validando_por_stdout(binario_anterior):
    """`--report` es un agregado, no un reemplazo: no puede romper lo que había."""
    ok, detalle = selftest.run(binario_anterior, expected_version=VERSION)

    assert ok, detalle


# --------------------------------------------------------------------------
# Lo que NO puede pasar: ningún camino que instale sin veredicto
# --------------------------------------------------------------------------

def test_un_binario_que_no_dice_nada_no_se_instala(mudo):
    """
    El riesgo del canal nuevo: leer vacío y tomarlo por bueno.

    Sin stdout y sin reporte no hay nada que leer, y eso tiene que ser un NO.
    """
    ok, detalle = selftest.run(mudo, expected_version=VERSION)

    assert not ok
    assert selftest.OK_MARKER in detalle, "el motivo del rechazo tiene que ser legible"


def test_un_binario_que_falla_no_se_instala_y_dice_por_que(roto):
    """El motivo del fallo tiene que llegar entero al log del updater."""
    ok, detalle = selftest.run(roto, expected_version=VERSION)

    assert not ok
    assert "No module named 'escpos'" in detalle, (
        f"el diagnóstico se perdió por el camino: {detalle!r}")


def test_una_version_distinta_no_se_instala(gui_windowed):
    """El canal nuevo no puede aflojar la verificación de versión."""
    ok, detalle = selftest.run(gui_windowed, expected_version="1.2.3")

    assert not ok
    assert "otra versión" in detalle


def test_la_marca_no_alcanza_si_el_proceso_salio_con_error(tmp_path):
    """
    Un binario que escribe la marca pero sale con código distinto de cero es
    un binario que falló. El código de salida manda.
    """
    mentiroso = binario_falso(tmp_path, "mentiroso", f"""
{GUI_SIN_STDOUT}
from fiscalberry.common.updater.cli_modes import _arg, _publicar_resultado
_publicar_resultado([{MARCA!r}], _arg(sys.argv, "--report"))
sys.exit(3)
""")

    ok, detalle = selftest.run(mentiroso, expected_version=VERSION)

    assert not ok
    assert "código 3" in detalle


def test_un_binario_colgado_no_se_instala(tmp_path):
    """Un binario que no termina no es un binario que anda."""
    colgado = binario_falso(tmp_path, "colgado", """
import time
time.sleep(10)
""")

    ok, detalle = selftest.run(colgado, expected_version=VERSION, timeout=2)

    assert not ok
    assert "no terminó" in detalle


def test_un_binario_que_no_se_puede_ejecutar_no_se_instala(tmp_path):
    """No poder correrlo es una respuesta, y la respuesta es que no."""
    ok, detalle = selftest.run(str(tmp_path / "no-existe"), expected_version=VERSION)

    assert not ok
    assert detalle, "un rechazo sin explicación no sirve para diagnosticar nada"


def test_el_veredicto_sobrevive_a_un_binario_ruidoso(tmp_path):
    """
    Un arranque que escupe miles de líneas no puede tapar el veredicto: los
    mensajes recortan la salida y el veredicto tiene que quedar del lado que
    sobrevive al recorte.
    """
    ruidoso = binario_falso(tmp_path, "ruidoso", f"""
from fiscalberry.common.updater.cli_modes import _arg, _publicar_resultado
for i in range(3000):
    print("ruido de arranque numero %s" % i)
_publicar_resultado([{MARCA!r}], _arg(sys.argv, "--report"))
sys.exit(0)
""")

    ok, detalle = selftest.run(ruidoso, expected_version=VERSION)

    assert ok, detalle
    assert MARCA in detalle


# --------------------------------------------------------------------------
# El archivo del reporte
# --------------------------------------------------------------------------

def test_el_reporte_va_a_un_directorio_privado_y_se_limpia(tmp_path):
    """
    La ruta no puede ser adivinable ni compartida: si lo fuera, bastaría con
    adelantarse a dejar ahí la marca de éxito para que un binario roto pasara
    el selftest y se instalara solo.
    """
    # El binario informa dónde le pidieron dejar el reporte y con qué permisos
    # está esa carpeta. Lo escribe en el reporte mismo para que llegue entero.
    espia = binario_falso(tmp_path, "espia", f"""
from fiscalberry.common.updater.cli_modes import _arg, _publicar_resultado
ruta = _arg(sys.argv, "--report")
carpeta = os.path.dirname(ruta)
_publicar_resultado(
    [{MARCA!r}, "CARPETA:%s" % carpeta, "MODO:%o" % (os.stat(carpeta).st_mode & 0o777)],
    ruta)
sys.exit(0)
""")

    ok, detalle = selftest.run(espia, expected_version=VERSION)
    assert ok, detalle

    informe = dict(l.split(":", 1) for l in detalle.splitlines() if ":" in l)
    carpeta = informe["CARPETA"]

    assert "fiscalberry-selftest-" in carpeta, (
        f"la carpeta del reporte no es una temporal propia: {carpeta}")
    assert not os.path.exists(carpeta), "el temporal tiene que quedar borrado"
    if os.name == "posix":
        # Solo el dueño: si el directorio fuera escribible por otros, alcanzaría
        # con dejar ahí la marca de éxito para que se instale un binario roto.
        assert informe["MODO"] == "700", (
            f"la carpeta del reporte quedó con permisos {informe['MODO']}")


@pytest.mark.parametrize("nombre,cuerpo", [
    ("explota", "sys.exit(1)"),
    ("cuelga", "import time\ntime.sleep(10)"),
])
def test_no_quedan_temporales_por_ningun_camino(tmp_path, nombre, cuerpo):
    """Incluidos los caminos de error, que son los que suelen filtrar."""
    import glob
    import tempfile

    antes = set(glob.glob(os.path.join(tempfile.gettempdir(), "fiscalberry-selftest-*")))
    selftest.run(binario_falso(tmp_path, nombre, cuerpo), timeout=2)
    despues = set(glob.glob(os.path.join(tempfile.gettempdir(), "fiscalberry-selftest-*")))

    assert despues == antes


# --------------------------------------------------------------------------
# El lado que escribe el veredicto
# --------------------------------------------------------------------------

def test_el_veredicto_se_escribe_por_los_dos_canales(tmp_path, capsys):
    """Archivo para la GUI, stdout para el binario de consola. Los dos."""
    ruta = tmp_path / "reporte.txt"

    _publicar_resultado([MARCA], str(ruta))

    assert ruta.read_text(encoding="utf-8").strip() == MARCA
    assert MARCA in capsys.readouterr().out


def test_sin_ruta_de_reporte_se_sigue_escribiendo_a_stdout(capsys):
    """Es lo que pasa cuando alguien corre `--selftest` a mano."""
    _publicar_resultado([MARCA])

    assert MARCA in capsys.readouterr().out


def test_si_el_reporte_no_se_puede_escribir_el_selftest_no_miente(tmp_path, capsys):
    """
    No poder escribir el reporte no puede hacer fallar al binario que sí anda
    (por eso no propaga), pero tampoco puede fabricar un éxito: el padre se
    queda sin marca y rechaza, que es el lado seguro del error.
    """
    inescribible = tmp_path / "no" / "existe" / "reporte.txt"

    _publicar_resultado([MARCA], str(inescribible))

    assert not inescribible.exists()
    assert MARCA in capsys.readouterr().out
