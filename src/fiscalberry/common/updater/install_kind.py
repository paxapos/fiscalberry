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
WINDOWS_GUI = "windows-gui"
WINDOWS_CLI = "windows-cli"
ANDROID = "android"
SOURCE = "source"

ASSET_BY_KIND = {
    LINUX_GUI: "fiscalberry-linux-gui.tar.gz",
    LINUX_CLI: "fiscalberry-linux-cli.tar.gz",
    WINDOWS_GUI: "fiscalberry-windows-gui.zip",
    WINDOWS_CLI: "fiscalberry-windows-cli.zip",
    ANDROID: "fiscalberry-android-gui.apk",
    # SOURCE no tiene asset: se actualiza desde el tarball de código del release.
}

# Nombre del ejecutable dentro del paquete comprimido, por variante.
BINARY_IN_ARCHIVE = {
    LINUX_GUI: "fiscalberry-gui",
    LINUX_CLI: "fiscalberry-cli",
    WINDOWS_GUI: "fiscalberry-gui.exe",
    WINDOWS_CLI: "fiscalberry-cli.exe",
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
        return WINDOWS_GUI if is_gui() else WINDOWS_CLI
    return LINUX_GUI if is_gui() else LINUX_CLI


def asset_name(kind):
    """Nombre del asset del release para esta variante, o None si no aplica."""
    return ASSET_BY_KIND.get(kind)


def binary_name(kind):
    """Nombre del ejecutable dentro del comprimido, o None si no aplica."""
    return BINARY_IN_ARCHIVE.get(kind)


def current_executable(kind):
    """
    Ruta del ejecutable que hay que reemplazar.

    Solo tiene sentido para las variantes empaquetadas: en SOURCE no hay un
    archivo único que reemplazar, y en ANDROID lo reemplaza el sistema.
    """
    if kind in (LINUX_GUI, LINUX_CLI, WINDOWS_GUI, WINDOWS_CLI):
        return os.path.realpath(sys.executable)
    return None
