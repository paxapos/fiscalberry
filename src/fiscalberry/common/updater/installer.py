"""
Actualizar la GUI de Windows con el instalador (FiscalberrySetup.exe).

Por qué no se sigue reemplazando la carpeta con el zip: el instalador de Inno
Setup deja `unins000.exe/.dat` y la entrada en "Aplicaciones" de Windows. El
updater del zip reemplazaba la carpeta entera y se llevaba puesto el
desinstalador, y el `DisplayVersion` quedaba desactualizado. Correr el setup
nuevo en silencio siempre pisa la versión anterior completa: nunca conviven
dos versiones, y el desinstalador queda al día.

Cómo encaja con el resto del updater:

1. Se descarga y verifica el setup (SHA256SUMS), como cualquier asset.
2. Se guarda también el setup de la versión que está corriendo, bajado de su
   release (por tag, sin usar la API) y verificado contra su SHA256SUMS. Es el respaldo: si la versión
   nueva no confirma el arranque, se reinstala ése en silencio. Las versiones
   publicadas antes del instalador no lo tienen, y entonces no hay reversión
   local (queda en el log).
3. Se lanza el setup desacoplado y este proceso termina para soltar el mutex
   de instancia única. El setup espera a que se libere antes de tocar
   archivos (ver [Code] en installer/fiscalberry.iss) y al terminar relanza
   Fiscalberry con `--minimized`.

A diferencia del zip, acá no hay selftest previo: un instalador no se puede
probar sin instalarlo. La CI prueba el binario instalado en cada release y,
en el equipo, la confirmación de arranque (commit_guard) cubre el resto.
"""

import hashlib
import os
import shutil
import subprocess
import tempfile

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.updater import commit_guard, release_source, staging
from fiscalberry.common.updater.appliers import RELAUNCH_LOCK_WAIT, ApplyError

logger = getLogger("Updater")

SETUP_ASSET = "FiscalberrySetup.exe"

# DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: el setup tiene que sobrevivir a
# este proceso, que termina enseguida para soltar el mutex.
_FLAGS_DESACOPLADO = 0x00000008 | 0x00000200


def installer_dir():
    """Donde se guardan los setups: fuera del staging, que se borra."""
    import platformdirs
    d = os.path.join(platformdirs.user_data_dir("fiscalberry"), "installer")
    os.makedirs(d, exist_ok=True)
    return d


def setup_path(version):
    return os.path.join(installer_dir(), f"FiscalberrySetup-{version}.exe")


def log_path(version):
    """Log del setup, junto al de Fiscalberry, para poder diagnosticarlo."""
    try:
        from fiscalberry.common.fiscalberry_logger import getServiceLogFilePath
        ruta_log = getServiceLogFilePath()
    except Exception:
        ruta_log = None
    if not ruta_log:
        return None
    return os.path.join(os.path.dirname(ruta_log), f"instalador-{version}.log")


def setup_command(setup, log=None, relanzar=True):
    """
    La línea de comandos del setup silencioso.

    - /VERYSILENT /SUPPRESSMSGBOXES: sin ventanas ni preguntas.
    - /NORESTART: nunca reiniciar la PC del local.
    - /CLOSEAPPLICATIONS: si algo más retiene archivos de la instalación, que
      el setup los cierre en vez de fallar.
    - /RELAUNCH=1: el [Run] del .iss vuelve a abrir Fiscalberry al terminar.
    """
    args = [setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
            "/CLOSEAPPLICATIONS"]
    if relanzar:
        args.append("/RELAUNCH=1")
    if log:
        args.append(f"/LOG={log}")
    return args


def lanzar_setup(args):
    """Arranca el setup desacoplado de este proceso."""
    entorno = dict(os.environ)
    # El Fiscalberry que relance el setup hereda este entorno: si el mutex
    # todavía no se liberó del todo, que espere en vez de rendirse.
    entorno["FISCALBERRY_LOCK_WAIT"] = RELAUNCH_LOCK_WAIT
    kwargs = {
        "env": entorno,
        "close_fds": True,
        # Nunca dentro de la carpeta instalada: Windows no deja tocar la
        # carpeta actual de un proceso vivo.
        "cwd": tempfile.gettempdir(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = _FLAGS_DESACOPLADO
    subprocess.Popen(args, **kwargs)


def _sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(256 * 1024), b""):
            h.update(trozo)
    return h.hexdigest()


def preparar_respaldo(version_actual, repo=release_source.DEFAULT_REPO):
    """
    Deja guardado y verificado el setup de la versión que está corriendo.

    Returns:
        La ruta al setup, o None si esta versión no tiene uno publicado (o no
        se pudo bajar). None significa "esta actualización no tiene reversión
        local": se avisa en el log y se actualiza igual.
    """
    tag = f"v{version_actual}"
    release = release_source.release_for_tag(
        tag, [SETUP_ASSET, release_source.CHECKSUMS_ASSET], repo)

    # El SHA256SUMS del tag dice si esa versión publicó instalador: las
    # anteriores al instalador no lo listan. Sin checksum tampoco se guarda
    # nada: un respaldo que no se puede verificar no sirve para revertir.
    esperado = release_source.fetch_checksums(release).get(SETUP_ASSET)
    if not esperado:
        logger.warning("La versión %s no publicó %s (o no se pudo verificar): "
                       "esta actualización no va a tener reversión local.",
                       version_actual, SETUP_ASSET)
        return None
    asset = release.asset(SETUP_ASSET)

    destino = setup_path(version_actual)
    if os.path.isfile(destino):
        try:
            if _sha256(destino) == esperado.lower():
                return destino
        except OSError:
            pass

    parcial = destino + ".part"
    try:
        staging.download(asset["url"], parcial, esperado,
                         expected_size=asset.get("size"))
        os.replace(parcial, destino)
    except (staging.StagingError, OSError) as e:
        logger.warning("No se pudo guardar el setup de %s como respaldo (%s): "
                       "esta actualización no va a tener reversión local.",
                       version_actual, e)
        try:
            os.remove(parcial)
        except OSError:
            pass
        return None

    logger.info("Setup de %s guardado como respaldo para revertir.", version_actual)
    return destino


def _limpiar_setups(conservar):
    """Borra setups guardados que ya no sirven. Nunca lanza."""
    conservar = {os.path.normcase(os.path.abspath(p)) for p in conservar if p}
    try:
        nombres = os.listdir(installer_dir())
    except OSError:
        return
    for nombre in nombres:
        ruta = os.path.join(installer_dir(), nombre)
        if os.path.normcase(os.path.abspath(ruta)) in conservar:
            continue
        try:
            if os.path.isfile(ruta):
                os.remove(ruta)
        except OSError:
            pass


def aplicar(setup_descargado, destino_dir, version, version_previa, respaldo):
    """
    Lanza la instalación de `version`. Después hay que cerrar este proceso.

    El setup se copia fuera del staging (que se borra al volver de acá) y se
    conserva: cuando salga la versión siguiente, ése va a ser su respaldo sin
    tener que bajarlo de nuevo.
    """
    copia = setup_path(version)
    try:
        if os.path.abspath(setup_descargado) != os.path.abspath(copia):
            shutil.copy2(setup_descargado, copia)
    except OSError as e:
        raise ApplyError(f"no se pudo preparar el instalador: {e}")

    _limpiar_setups(conservar={copia, respaldo})

    if not respaldo:
        logger.warning("Actualizando a %s SIN reversión local: si la versión "
                       "nueva no arranca, hay que reinstalar a mano.", version)

    commit_guard.arm(version, version_previa, destino_dir, respaldo,
                     method=commit_guard.METODO_INSTALADOR)
    try:
        lanzar_setup(setup_command(copia, log_path(version)))
    except Exception as e:
        commit_guard.clear()
        raise ApplyError(f"no se pudo lanzar el instalador: {e}")

    logger.info("Instalador de %s lanzado; Fiscalberry se cierra para que "
                "pueda reemplazar la versión %s.", version, version_previa)
    return True


def revertir(pendiente):
    """
    La versión nueva no confirmó el arranque: reinstalar la anterior.

    Returns:
        True si el setup anterior quedó lanzado (este proceso debe cerrarse).
    """
    if not pendiente.backup_exists():
        logger.error(
            "La versión %s no logró arrancar y no hay instalador de %s guardado "
            "(se publicó antes del instalador o no se pudo bajar): no se puede "
            "revertir solo. Hay que reinstalar Fiscalberry a mano.",
            pendiente.version, pendiente.previous_version)
        commit_guard.mark_reverted(pendiente.version)
        commit_guard.clear()
        return False

    try:
        lanzar_setup(setup_command(pendiente.backup,
                                   log_path(pendiente.previous_version)))
    except Exception as e:
        # La marca queda: el próximo arranque lo vuelve a intentar.
        logger.critical("No se pudo lanzar el instalador de %s para revertir: %s",
                        pendiente.previous_version, e)
        return False

    commit_guard.mark_reverted(pendiente.version)
    commit_guard.clear()
    logger.warning("Reinstalando %s en silencio; este proceso se cierra.",
                   pendiente.previous_version)
    return True
