"""
Probar el binario nuevo ANTES de instalarlo.

Compilar sin errores no prueba nada: el modo de falla real de un binario de
PyInstaller es arrancar y morir en el primer import que el empaquetador no
detectó. Por eso, antes de reemplazar nada, se ejecuta el binario nuevo en modo
`--selftest` y se exige que salga limpio.

El selftest corre en el binario NUEVO, en un proceso aparte. Si explota, se
descarta la descarga y el dispositivo sigue con la versión que tenía.
"""

import os
import stat
import subprocess

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("Updater")

# Marca que imprime el modo selftest. Se exige encontrarla en la salida: un
# exit code 0 solo no alcanza (un binario que no arranca puede devolver 0 por
# accidente en algunos empaquetados).
OK_MARKER = "FISCALBERRY_SELFTEST_OK"

SELFTEST_TIMEOUT = 120


def make_executable(path):
    """chmod +x, necesario porque el tar.gz puede perder el bit de ejecución."""
    try:
        modo = os.stat(path).st_mode
        os.chmod(path, modo | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception as e:
        logger.debug(f"No se pudo dar permiso de ejecución a {path}: {e}")


def run(binario, expected_version=None, timeout=SELFTEST_TIMEOUT):
    """
    Ejecuta `binario --selftest`.

    Devuelve (ok, detalle). `ok` False significa "no instalar esto".
    """
    make_executable(binario)

    entorno = dict(os.environ)
    # Que el selftest no dependa de tener un display, ni ensucie la consola.
    entorno["KIVY_NO_CONSOLELOG"] = "1"
    entorno["KIVY_NO_ARGS"] = "1"
    entorno["FISCALBERRY_SELFTEST"] = "1"

    try:
        proc = subprocess.run(
            [binario, "--selftest"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=entorno,
        )
    except subprocess.TimeoutExpired:
        return False, f"el selftest no terminó en {timeout}s (binario colgado)"
    except Exception as e:
        return False, f"no se pudo ejecutar el binario nuevo: {e}"

    salida = (proc.stdout or b"").decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        return False, f"el selftest salió con código {proc.returncode}: {salida[-400:]}"

    if OK_MARKER not in salida:
        return False, f"el selftest no imprimió {OK_MARKER}: {salida[-400:]}"

    if expected_version:
        esperado = f"{OK_MARKER} {expected_version}"
        if esperado not in salida:
            return False, (
                f"el binario nuevo dice ser otra versión "
                f"(se esperaba '{esperado}', salida: {salida[-200:]})")

    return True, salida[-200:]


def selftest_report(version):
    """
    Lo que imprime el proceso cuando se lo invoca con --selftest.

    Se mantiene acá para que el productor y el consumidor de la marca no se
    desincronicen.
    """
    return f"{OK_MARKER} {version}"
