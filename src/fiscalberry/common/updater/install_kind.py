"""
Qué tipo de instalación es ésta, y por lo tanto qué artefacto le corresponde.

Los nombres de los assets salen de `.github/workflows/build-release.yml`. Si
allá se renombra un artefacto, hay que tocar ASSET_BY_KIND o los dispositivos
dejan de encontrar su actualización (fallan en silencio: "no hay nada para mí").
"""

import os
import sys

# Variantes soportadas.
LINUX_GUI = "linux-gui"
LINUX_CLI = "linux-cli"
# GUI portable de Windows (zip). Ya no la detecta ningún proceso: la sigue
# buscando el updater de las 3.6.x, así que el zip se publica al menos un
# release más para que esas instalaciones reciban el updater nuevo (#187).
WINDOWS_GUI = "windows-gui"
WINDOWS_CLI = "windows-cli"
# GUI de Windows actualizada con el instalador de Inno Setup: toda GUI
# congelada en Windows, instalada o portable (las portables migran así a la
# ubicación instalada).
WINDOWS_INSTALLER = "windows-installer"
ANDROID = "android"
SOURCE = "source"

ASSET_BY_KIND = {
    LINUX_GUI: "fiscalberry-linux-gui.tar.gz",
    LINUX_CLI: "fiscalberry-linux-cli.tar.gz",
    WINDOWS_GUI: "fiscalberry-windows-gui.zip",
    WINDOWS_CLI: "fiscalberry-windows-cli.zip",
    WINDOWS_INSTALLER: "FiscalberrySetup.exe",
    ANDROID: "fiscalberry-android-gui.apk",
    # SOURCE no tiene asset: se actualiza desde el tarball de código del release.
}

# Nombre del ejecutable dentro del paquete comprimido (o del que deja
# instalado el setup), por variante.
BINARY_IN_ARCHIVE = {
    LINUX_GUI: "fiscalberry-gui",
    LINUX_CLI: "fiscalberry-cli",
    WINDOWS_GUI: "fiscalberry-gui.exe",
    WINDOWS_CLI: "fiscalberry-cli.exe",
    WINDOWS_INSTALLER: "fiscalberry-gui.exe",
}

# AppId de installer/fiscalberry.iss. Inno Setup registra la instalación en
# HKCU\...\Uninstall\{AppId}_is1 (instalación por usuario).
INNO_APP_ID = "{55BB025A-ED36-4DB6-A2A3-706DD36AB936}"
UNINSTALL_KEY = (
    "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + INNO_APP_ID + "_is1"
)

# Los builds son ONEDIR: el comprimido trae una CARPETA con el ejecutable y sus
# dependencias al lado (ver fiscalberry-cli.spec). Por eso el updater reemplaza
# el directorio completo y no un archivo suelto.
APP_DIR_IN_ARCHIVE = {
    LINUX_GUI: "fiscalberry-gui",
    LINUX_CLI: "fiscalberry-cli",
    WINDOWS_GUI: "fiscalberry-gui",
    WINDOWS_CLI: "fiscalberry-cli",
}


def is_android():
    """
    Android no se detecta por `sys.platform` (dice 'linux'). p4a define estas
    variables de entorno en ambos procesos, el de la UI y el del servicio.
    """
    return bool(os.environ.get("ANDROID_ARGUMENT") or os.environ.get("ANDROID_APP_PATH"))


def is_frozen():
    """True si corre como binario de PyInstaller (no desde el código fuente)."""
    return getattr(sys, "frozen", False)


def is_gui():
    """
    Si el binario que se está ejecutando es el de la GUI.

    Se mira el NOMBRE del ejecutable, no si Kivy está importado: el binario GUI
    puede estar arrancando y todavía no haber creado la App, y el CLI puede
    tener kivy instalado en el entorno sin usarlo.
    """
    nombre = os.path.basename(sys.executable or "").lower()
    return "gui" in nombre


def detect():
    """Devuelve la variante de instalación de este proceso."""
    if is_android():
        return ANDROID
    if not is_frozen():
        # Instalado desde código: Raspberry, o un dev corriendo `pip install -e .`
        return SOURCE
    if sys.platform.startswith("win"):
        return WINDOWS_INSTALLER if is_gui() else WINDOWS_CLI
    return LINUX_GUI if is_gui() else LINUX_CLI


def asset_name(kind):
    """Nombre del asset del release para esta variante, o None si no aplica."""
    return ASSET_BY_KIND.get(kind)


def binary_name(kind):
    """Nombre del ejecutable dentro del comprimido, o None si no aplica."""
    return BINARY_IN_ARCHIVE.get(kind)


def app_dir_name(kind):
    """Nombre de la carpeta de la app dentro del comprimido, o None."""
    return APP_DIR_IN_ARCHIVE.get(kind)


def is_packaged(kind):
    """True si esta variante se distribuye como carpeta empaquetada."""
    return kind in (LINUX_GUI, LINUX_CLI, WINDOWS_GUI, WINDOWS_CLI, WINDOWS_INSTALLER)


def current_executable(kind):
    """
    Ruta del ejecutable en ejecución.

    Solo tiene sentido para las variantes empaquetadas: en SOURCE no hay un
    ejecutable propio, y en ANDROID lo maneja el sistema.
    """
    if is_packaged(kind):
        return os.path.realpath(sys.executable)
    return None


def current_app_dir(kind):
    """
    Carpeta de instalación que hay que reemplazar al actualizar.

    En onedir el ejecutable vive dentro de su carpeta, junto a `_internal/`
    con todas las dependencias:

        fiscalberry-cli/
            fiscalberry-cli      <- sys.executable
            _internal/...

    Reemplazar solo el ejecutable dejaría un `_internal` de la versión vieja
    al lado del binario nuevo — combinación que puede no arrancar. Por eso se
    cambia el directorio entero, de una.
    """
    ejecutable = current_executable(kind)
    if not ejecutable:
        return None
    return os.path.dirname(ejecutable)


def installed_location(winreg_module=None):
    """
    Carpeta donde el instalador dejó la GUI de Windows, o None.

    Se lee del registro (`InstallLocation` de la entrada de desinstalación) y no
    se asume %LOCALAPPDATA%\\Programs\\Fiscalberry: en el instalador interactivo
    el usuario puede elegir otra carpeta.
    """
    try:
        winreg = winreg_module
        if winreg is None:
            import winreg  # noqa: F811 (solo existe en Windows)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as clave:
            valor, _tipo = winreg.QueryValueEx(clave, "InstallLocation")
    except Exception:
        return None
    valor = str(valor or "").strip().rstrip("\\/")
    return valor or None
