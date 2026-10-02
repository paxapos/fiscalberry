# coding=utf-8
from pathlib import Path

from fiscalberry.common.updater.selftest import OK_MARKER
from fiscalberry.desktop.main import consume_start_minimized


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "fiscalberry.iss"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "build-release.yml"


def test_consume_minimized_antes_de_cargar_kivy():
    argv = ["fiscalberry-gui.exe", "--minimized", "--otro"]

    assert consume_start_minimized(argv) is True
    assert argv == ["fiscalberry-gui.exe", "--otro"]


def test_arranque_normal_no_modifica_los_argumentos():
    argv = ["fiscalberry-gui.exe", "--otro"]

    assert consume_start_minimized(argv) is False
    assert argv == ["fiscalberry-gui.exe", "--otro"]


def test_instalador_es_por_usuario_y_empaqueta_onedir_completo():
    contenido = INSTALLER.read_text(encoding="utf-8")

    assert "PrivilegesRequired=lowest" in contenido
    assert "DefaultDirName={localappdata}\\Programs\\Fiscalberry" in contenido
    assert 'Source: "..\\dist\\fiscalberry-gui\\*"' in contenido
    assert "recursesubdirs" in contenido


def test_instalador_configura_inicio_minimizado_y_nombre_estable():
    contenido = INSTALLER.read_text(encoding="utf-8")

    assert "OutputBaseFilename=FiscalberrySetup" in contenido
    assert 'ValueName: "Fiscalberry"' in contenido
    assert '--minimized' in contenido


def test_release_compila_y_prueba_el_instalador():
    contenido = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "installer/fiscalberry.iss" in contenido
    assert "FiscalberrySetup.exe" in contenido
    assert "/VERYSILENT" in contenido
    assert "--selftest" in contenido
    assert "unins000.exe" in contenido


def _paso(contenido, nombre):
    """Texto de un step del workflow, desde su `- name:` hasta el siguiente."""
    inicio = contenido.index(f"- name: {nombre}")
    fin = contenido.find("- name: ", inicio + 1)
    return contenido[inicio:fin if fin != -1 else None]


def test_el_selftest_del_instalado_espera_al_exe_y_exige_la_marca_real():
    """
    Tres cosas que hacían que el paso no pudiera pasar nunca:

    - `& exe` no espera a un ejecutable de subsistema GUI y deja $LASTEXITCODE
      sin asignar: hay que usar Start-Process -Wait.
    - Sin KIVY_NO_ARGS, Kivy aborta con código 2 al ver `--selftest` en argv.
    - Buscaba "SELFTEST OK" cuando la marca real es OK_MARKER + versión.
    """
    paso = _paso(RELEASE_WORKFLOW.read_text(encoding="utf-8"), "Test Windows Installer")

    assert '-ArgumentList "--selftest"' in paso
    assert "-Wait -PassThru" in paso
    assert '& "$installDir' not in paso
    assert "KIVY_NO_ARGS: 1" in paso
    assert f"{OK_MARKER} ${{{{ needs.version.outputs.version }}}}" in paso
    assert "SELFTEST OK" not in paso


def test_release_publica_el_instalador():
    contenido = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "name: fiscalberry-windows-installer" in contenido
    assert "./artifacts/FiscalberrySetup.exe" in contenido