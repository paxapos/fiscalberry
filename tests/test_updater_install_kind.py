# coding=utf-8
"""
Qué instalación es ésta y qué artefacto le toca.

El test que más valor tiene acá es el último: verifica contra el workflow real
que los nombres de los assets coinciden. Si alguien renombra un artefacto en la
CI, los dispositivos de esa plataforma dejarían de encontrar su actualización
**en silencio** (para ellos sería "este release no trae nada para mí"), y nadie
se enteraría hasta que alguien mire por qué una flota entera quedó vieja.
"""

import os
import re

import pytest

from fiscalberry.common.updater import install_kind


REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "build-release.yml")


def test_android_se_detecta_por_las_variables_de_p4a(monkeypatch):
    """sys.platform en Android dice 'linux'; hay que mirar el entorno."""
    monkeypatch.setenv("ANDROID_ARGUMENT", "/data/app")
    assert install_kind.detect() == install_kind.ANDROID


def test_sin_congelar_es_instalacion_desde_codigo(monkeypatch):
    """Raspberry y desarrollo: no hay binario único que reemplazar."""
    monkeypatch.delenv("ANDROID_ARGUMENT", raising=False)
    monkeypatch.delenv("ANDROID_APP_PATH", raising=False)
    monkeypatch.setattr(install_kind.sys, "frozen", False, raising=False)
    monkeypatch.setattr(install_kind, "is_frozen", lambda: False)

    assert install_kind.detect() == install_kind.SOURCE
    assert install_kind.current_executable(install_kind.SOURCE) is None


@pytest.mark.parametrize("ejecutable,plataforma,esperado", [
    ("/opt/fb/fiscalberry-cli", "linux", install_kind.LINUX_CLI),
    ("/opt/fb/fiscalberry-gui", "linux", install_kind.LINUX_GUI),
    (r"C:\fb\fiscalberry-cli.exe", "win32", install_kind.WINDOWS_CLI),
    # Toda GUI de Windows se actualiza con el instalador, esté instalada o sea
    # una copia portable del zip (#187): así las portables migran.
    (r"C:\fb\fiscalberry-gui.exe", "win32", install_kind.WINDOWS_INSTALLER),
    (r"C:\Users\x\AppData\Local\Programs\Fiscalberry\fiscalberry-gui.exe",
     "win32", install_kind.WINDOWS_INSTALLER),
])
def test_variante_segun_el_ejecutable(monkeypatch, ejecutable, plataforma, esperado):
    monkeypatch.delenv("ANDROID_ARGUMENT", raising=False)
    monkeypatch.delenv("ANDROID_APP_PATH", raising=False)
    monkeypatch.setattr(install_kind, "is_frozen", lambda: True)
    monkeypatch.setattr(install_kind.sys, "executable", ejecutable)
    monkeypatch.setattr(install_kind.sys, "platform", plataforma)

    assert install_kind.detect() == esperado


def test_toda_variante_empaquetada_sabe_su_asset_y_su_binario():
    for kind in (install_kind.LINUX_CLI, install_kind.LINUX_GUI,
                 install_kind.WINDOWS_CLI, install_kind.WINDOWS_GUI,
                 install_kind.WINDOWS_INSTALLER):
        assert install_kind.asset_name(kind), f"{kind} sin asset"
        assert install_kind.binary_name(kind), f"{kind} sin binario"


def test_source_no_tiene_asset():
    """Se actualiza con pip desde el tarball de código, no con un artefacto."""
    assert install_kind.asset_name(install_kind.SOURCE) is None


@pytest.mark.skipif(not os.path.exists(WORKFLOW), reason="sin workflow en el checkout")
def test_los_assets_existen_en_el_workflow_de_release():
    """
    Guarda contra el modo de falla silencioso: renombrar un artefacto en la CI
    y dejar a esa plataforma sin actualizaciones sin que nadie lo note.
    """
    with open(WORKFLOW, "r", encoding="utf-8") as fh:
        contenido = fh.read()

    for kind, asset in install_kind.ASSET_BY_KIND.items():
        assert asset in contenido, (
            f"El asset '{asset}' de la variante {kind} no aparece en "
            f"build-release.yml: los dispositivos de esa plataforma no "
            f"encontrarían su actualización.")


@pytest.mark.skipif(not os.path.exists(WORKFLOW), reason="sin workflow en el checkout")
def test_el_workflow_publica_los_checksums():
    """Sin SHA256SUMS el updater se niega a instalar: es parte del contrato."""
    with open(WORKFLOW, "r", encoding="utf-8") as fh:
        contenido = fh.read()

    assert "SHA256SUMS" in contenido
    assert re.search(r"sha256sum\s", contenido), \
        "el workflow no genera los checksums"


def test_la_gui_de_windows_se_actualiza_con_el_instalador():
    assert install_kind.asset_name(install_kind.WINDOWS_INSTALLER) == "FiscalberrySetup.exe"
    assert install_kind.binary_name(install_kind.WINDOWS_INSTALLER) == "fiscalberry-gui.exe"


@pytest.mark.skipif(not os.path.exists(WORKFLOW), reason="sin workflow en el checkout")
def test_el_zip_portable_se_sigue_publicando_en_la_transicion():
    """
    Las 3.6.x buscan fiscalberry-windows-gui.zip con su updater viejo: si el
    release deja de traerlo antes de tiempo, nunca reciben el updater nuevo.
    """
    with open(WORKFLOW, "r", encoding="utf-8") as fh:
        contenido = fh.read()
    assert "./artifacts/fiscalberry-windows-gui.zip" in contenido
    assert "./artifacts/FiscalberrySetup.exe" in contenido


class _WinregFalso:
    HKEY_CURRENT_USER = "HKCU"

    def __init__(self, valores):
        self.valores = valores
        self.abiertas = []

    def OpenKey(self, raiz, subclave):
        self.abiertas.append((raiz, subclave))
        if subclave not in self.valores:
            raise FileNotFoundError(subclave)
        valores = self.valores[subclave]

        class _Clave:
            def __enter__(self_inner):
                return valores

            def __exit__(self_inner, *exc):
                return False

        return _Clave()

    def QueryValueEx(self, clave, nombre):
        if nombre not in clave:
            raise FileNotFoundError(nombre)
        return clave[nombre], 1


def test_la_ubicacion_instalada_sale_del_registro_de_inno_setup():
    winreg = _WinregFalso({install_kind.UNINSTALL_KEY: {
        "InstallLocation": "C:\\Users\\x\\AppData\\Local\\Programs\\Fiscalberry\\",
    }})

    ubicacion = install_kind.installed_location(winreg_module=winreg)

    assert ubicacion == "C:\\Users\\x\\AppData\\Local\\Programs\\Fiscalberry"
    assert winreg.abiertas == [("HKCU", install_kind.UNINSTALL_KEY)]


def test_sin_instalacion_no_hay_ubicacion():
    assert install_kind.installed_location(winreg_module=_WinregFalso({})) is None


def test_el_app_id_coincide_con_el_del_instalador():
    """Si se cambia el AppId del .iss, la migración y la reversión se pierden."""
    iss = os.path.join(REPO, "installer", "fiscalberry.iss")
    with open(iss, "r", encoding="utf-8") as fh:
        assert "AppId={" + install_kind.INNO_APP_ID in fh.read()
