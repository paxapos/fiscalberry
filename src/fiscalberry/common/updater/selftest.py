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
import tempfile

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

    codigo, salida, error = _ejecutar(binario, entorno, timeout)
    if error:
        return False, error

    if codigo != 0:
        return False, f"el selftest salió con código {codigo}: {salida[-400:]}"

    if OK_MARKER not in salida:
        return False, f"el selftest no imprimió {OK_MARKER}: {salida[-400:]}"

    if expected_version:
        esperado = f"{OK_MARKER} {expected_version}"
        if esperado not in salida:
            return False, (
                f"el binario nuevo dice ser otra versión "
                f"(se esperaba '{esperado}', salida: {salida[-200:]})")

    return True, salida[-200:]


def _ejecutar(binario, entorno, timeout):
    """
    Corre `binario --selftest` y junta lo que haya dicho.

    Devuelve (codigo_de_salida, salida, error). `error` no vacío significa que
    el proceso ni siquiera llegó a terminar, y los otros dos no sirven.

    El binario de la GUI se compila sin consola (`console=False`), así que su
    stdout no llega a ningún lado y la marca de éxito se perdía: todo selftest
    de la GUI en Windows daba por fallado y esa GUI no podía actualizarse
    nunca. Por eso se le pasa además un archivo donde dejar el resultado.

    El archivo va en un directorio temporal propio y no en una ruta fija: el
    veredicto de una actualización no puede depender de un nombre predecible
    en un directorio que cualquiera puede escribir, o bastaría con adelantarse
    a crearlo para que un binario roto pase el selftest.
    """
    with tempfile.TemporaryDirectory(prefix="fiscalberry-selftest-") as carpeta:
        reporte = os.path.join(carpeta, "reporte.txt")

        try:
            proc = subprocess.run(
                [binario, "--selftest", "--report", reporte],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                env=entorno,
            )
        except subprocess.TimeoutExpired:
            return None, "", f"el selftest no terminó en {timeout}s (binario colgado)"
        except Exception as e:
            return None, "", f"no se pudo ejecutar el binario nuevo: {e}"

        consola = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
        del_archivo = _leer_reporte(reporte)

    # El reporte va al final a propósito: los mensajes de error recortan la
    # salida por el final (`salida[-400:]`) y ahí es donde tiene que quedar el
    # veredicto, no el ruido de arranque del binario.
    salida = "\n".join(p for p in (consola, del_archivo) if p).strip()
    return proc.returncode, salida, ""


def _leer_reporte(ruta):
    """Contenido del archivo de reporte, o cadena vacía si no está."""
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except Exception:
        return ""


def selftest_report(version):
    """
    Lo que imprime el proceso cuando se lo invoca con --selftest.

    Se mantiene acá para que el productor y el consumidor de la marca no se
    desincronicen.
    """
    return f"{OK_MARKER} {version}"
