# coding=utf-8
from pathlib import Path

from fiscalberry.desktop.main import consume_start_minimized


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "fiscalberry.iss"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "build-release.yml"
INSTALLER_WORKFLOW = ROOT / ".github" / "workflows" / "windows-installer.yml"
INSTALLER_TEST = ROOT / "build_tools" / "test-windows-installer.ps1"


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
    for workflow in (RELEASE_WORKFLOW, INSTALLER_WORKFLOW):
        contenido = workflow.read_text(encoding="utf-8")
        assert "installer/fiscalberry.iss" in contenido, workflow.name
        assert "test-windows-installer.ps1" in contenido, workflow.name


def test_la_prueba_cubre_instalacion_actualizacion_y_desinstalacion():
    """Criterio de aceptación de #187 para el job del instalador."""
    prueba = INSTALLER_TEST.read_text(encoding="utf-8")

    assert "/VERYSILENT" in prueba
    assert "--selftest" in prueba
    # El selftest escribe esta marca (updater/selftest.py OK_MARKER).
    assert "FISCALBERRY_SELFTEST_OK" in prueba
    # Actualización con la app abierta: el setup tiene que esperar el mutex.
    assert "Local\\FiscalberrySingleInstance" in prueba
    assert "/RELAUNCH=1" in prueba
    assert "unins000.exe" in prueba
    # La desinstalación conserva la vinculación.
    assert "config.ini" in prueba


def test_release_publica_el_instalador():
    contenido = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "name: fiscalberry-windows-installer" in contenido
    assert "./artifacts/FiscalberrySetup.exe" in contenido

def _iss():
    # UTF-8 con BOM: así lo lee cualquier Inno Setup 6.
    return INSTALLER.read_text(encoding="utf-8-sig")


def test_el_mutex_del_instalador_es_el_de_la_app():
    """
    El setup sabe que Fiscalberry está abierto por el mutex que crea la app.
    Si los nombres divergen, pisaría los archivos de un Fiscalberry abierto.
    """
    from fiscalberry.common.single_instance import WINDOWS_MUTEX_NAME

    assert f'#define AppMutex "{WINDOWS_MUTEX_NAME}"' in _iss()
    assert "CheckForMutexes('{#AppMutex}')" in _iss()


def test_el_setup_espera_a_que_se_cierre_antes_de_instalar_o_desinstalar():
    contenido = _iss()
    assert "function InitializeSetup(): Boolean;" in contenido
    assert "function InitializeUninstall(): Boolean;" in contenido
    assert "EsperaSilenciosaSeg = 60" in contenido
    assert "MB_RETRYCANCEL" in contenido


def test_cada_version_reemplaza_el_internal_de_la_anterior():
    contenido = _iss()
    assert "[InstallDelete]" in contenido
    assert 'Type: filesandordirs; Name: "{app}\\_internal"' in contenido


def test_relanza_en_silencio_solo_si_lo_pide_el_updater():
    lineas = [l for l in _iss().splitlines() if l.startswith("Filename:")]
    relanzar = [l for l in lineas if "Check: DebeRelanzar" in l]

    assert len(relanzar) == 1
    # Sin skipifsilent: la actualización del updater ES silenciosa.
    assert "skipifsilent" not in relanzar[0]
    assert 'Parameters: "--minimized"' in relanzar[0]
    assert "ExpandConstant('{param:RELAUNCH|0}') = '1'" in _iss()


def test_la_linea_de_comandos_del_updater_pide_relanzar():
    from fiscalberry.common.updater.appliers import INSTALLER_SILENT_ARGS

    assert "/RELAUNCH=1" in INSTALLER_SILENT_ARGS
    assert "/CLOSEAPPLICATIONS" in INSTALLER_SILENT_ARGS
    assert "/VERYSILENT" in INSTALLER_SILENT_ARGS


def test_el_script_es_utf8_con_bom():
    assert INSTALLER.read_bytes().startswith(b"\xef\xbb\xbf")
