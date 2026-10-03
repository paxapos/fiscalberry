# coding=utf-8
from pathlib import Path

from fiscalberry.common.updater.selftest import OK_MARKER
from fiscalberry.desktop.main import consume_start_minimized


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "fiscalberry.iss"
PRUEBA_INSTALADOR = ROOT / "installer" / "test_installer.ps1"
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
    contenido = INSTALLER.read_text(encoding="utf-8-sig")

    assert "PrivilegesRequired=lowest" in contenido
    assert "DefaultDirName={localappdata}\\Programs\\Fiscalberry" in contenido
    assert 'Source: "..\\dist\\fiscalberry-gui\\*"' in contenido
    assert "recursesubdirs" in contenido


def test_instalador_configura_inicio_minimizado_y_nombre_estable():
    contenido = INSTALLER.read_text(encoding="utf-8-sig")

    assert "OutputBaseFilename=FiscalberrySetup" in contenido
    assert 'ValueName: "Fiscalberry"' in contenido
    assert '--minimized' in contenido


def test_release_compila_y_prueba_el_instalador():
    contenido = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "installer/fiscalberry.iss" in contenido
    paso = _paso(contenido, "Test Windows Installer")
    assert "./installer/test_installer.ps1" in paso
    assert "-Version \"${{ needs.version.outputs.version }}\"" in paso
    # Sin esto Kivy aborta con código 2 al ver `--selftest` en argv.
    assert "KIVY_NO_ARGS: 1" in paso


def _paso(contenido, nombre):
    """Texto de un step del workflow, desde su `- name:` hasta el siguiente."""
    inicio = contenido.index(f"- name: {nombre}")
    fin = contenido.find("- name: ", inicio + 1)
    return contenido[inicio:fin if fin != -1 else None]


def test_la_prueba_del_instalador_espera_al_exe_y_exige_la_marca_real():
    """
    Lo que hacía que la prueba no pudiera pasar nunca:

    - `& exe` no espera a un ejecutable de subsistema GUI y deja $LASTEXITCODE
      sin asignar: hay que usar Start-Process -Wait.
    - Buscaba "SELFTEST OK" cuando la marca real es OK_MARKER + versión.
    """
    script = PRUEBA_INSTALADOR.read_text(encoding="utf-8")

    assert "-Wait -PassThru" in script
    assert "$LASTEXITCODE" not in script.split("param(", 1)[1]
    assert '@("--selftest", "--report"' in script
    assert f'"{OK_MARKER} $Version"' in script
    assert "SELFTEST OK" not in script


def test_la_prueba_cubre_actualizacion_relanzado_y_desinstalacion():
    """Los criterios de aceptación de #187 para el instalador."""
    script = PRUEBA_INSTALADOR.read_text(encoding="utf-8")

    # Actualización silenciosa con la app abierta: el setup espera al mutex.
    assert '"Local\\FiscalberrySingleInstance"' in script
    assert "New-Object System.Threading.Mutex" in script
    assert "/RELAUNCH=1" in script and "/CLOSEAPPLICATIONS" in script
    # La actualización conserva el desinstalador.
    assert "La actualización borró unins000.exe" in script
    # Relanzado y desinstalación que conserva la vinculación.
    assert "=== Iniciando Fiscalberry GUI ===" in script
    assert "config.ini" in script


def test_instalador_espera_al_mutex_y_relanza_en_silencio():
    from fiscalberry.common.single_instance import WINDOWS_MUTEX_NAME

    contenido = INSTALLER.read_text(encoding="utf-8-sig")

    assert f"'{WINDOWS_MUTEX_NAME}'" in contenido
    assert "function InitializeSetup(): Boolean;" in contenido
    assert "function InitializeUninstall(): Boolean;" in contenido
    assert "CheckForMutexes(MutexFiscalberry)" in contenido
    # Relanzado del auto-updater: sin skipifsilent y solo con /RELAUNCH=1.
    relanzar = next(l for l in contenido.splitlines() if "Check: DebeRelanzar" in l)
    assert 'Parameters: "--minimized"' in relanzar
    assert "skipifsilent" not in relanzar
    assert "{param:RELAUNCH|0}" in contenido


def test_instalador_borra_restos_de_la_version_anterior_y_habla_espanol():
    contenido = INSTALLER.read_text(encoding="utf-8-sig")

    assert '[InstallDelete]\nType: filesandordirs; Name: "{app}\\_internal"' in contenido
    assert 'MessagesFile: "compiler:Languages\\Spanish.isl"' in contenido


def test_instalador_tiene_bom_para_que_inno_lea_los_acentos():
    assert INSTALLER.read_bytes().startswith(b"\xef\xbb\xbf")


def test_release_publica_el_instalador():
    contenido = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "name: fiscalberry-windows-installer" in contenido
    assert "./artifacts/FiscalberrySetup.exe" in contenido