# coding=utf-8
"""
Configuración compartida de pytest para los tests de Fiscalberry.

Agrega `src/` al sys.path para poder importar el paquete `fiscalberry`
sin necesidad de instalarlo en modo editable.

Además aísla los directorios del usuario (config, datos, logs): Configberry()
es un singleton que se crea al importar el paquete y lee/escribe
`<config del usuario>/Fiscalberry/config.ini`. Sin este aislamiento los tests
leían (y podían modificar) el config.ini real de quien los corre, y su
resultado dependía de ese archivo. Tiene que correr ANTES de importar
`fiscalberry`, por eso va a nivel de módulo y no en un fixture.
"""

import atexit
import os
import shutil
import sys
import tempfile

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def _aislar_directorios_de_usuario():
    base = tempfile.mkdtemp(prefix="fiscalberry-tests-")
    atexit.register(shutil.rmtree, base, ignore_errors=True)

    config = os.path.join(base, "config")
    datos = os.path.join(base, "data")
    cache = os.path.join(base, "cache")

    # Lo que resuelve platformdirs (XDG en Linux, HOME en macOS) y el código que
    # expande "~". Los subprocesos que lanzan algunos tests heredan estas variables.
    # Los tests que necesitan su propio directorio lo pisan con monkeypatch.setenv.
    # Limitación: en Windows platformdirs usa la API del sistema y no lee estas
    # variables (los tests de config ya asumen XDG_CONFIG_HOME, ver
    # test_config_primer_arranque).
    entorno = {
        "HOME": base,
        "USERPROFILE": base,
        "XDG_CONFIG_HOME": config,
        "XDG_DATA_HOME": datos,
        "XDG_CACHE_HOME": cache,
        "XDG_STATE_HOME": os.path.join(base, "state"),
        "APPDATA": config,
        "LOCALAPPDATA": datos,
    }
    os.environ.update(entorno)


_aislar_directorios_de_usuario()
