"""
Bajar el artefacto a un lugar aparte, verificarlo y recién ahí desempaquetarlo.

Nada de esto toca la instalación viva: todo pasa en un directorio de staging que
se borra al terminar. Si algo falla a mitad de camino, el dispositivo sigue
corriendo la versión que tenía.
"""

import hashlib
import os
import shutil
import tarfile
import tempfile
import zipfile

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("Updater")

HTTP_TIMEOUT = 60
CHUNK = 256 * 1024
# Tope de tamaño para no llenar el disco de una Raspberry si el asset viene mal.
MAX_ASSET_BYTES = 300 * 1024 * 1024


class StagingError(Exception):
    pass


def staging_dir():
    """Directorio de trabajo, al lado de los datos de la app (mismo filesystem)."""
    import platformdirs
    d = os.path.join(platformdirs.user_data_dir("fiscalberry"), "update-staging")
    os.makedirs(d, exist_ok=True)
    return d


def cleanup(path):
    """Borra el staging. Nunca lanza: limpiar no puede romper la actualización."""
    try:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        logger.debug(f"No se pudo limpiar el staging {path}: {e}")


def download(url, destino, expected_sha256, session=None, expected_size=None):
    """
    Descarga `url` a `destino` verificando el hash mientras baja.

    El hash se calcula sobre el stream, así que no hace falta releer el archivo
    y un contenido cambiado se detecta aunque el tamaño coincida.
    """
    import requests

    if not expected_sha256:
        raise StagingError("no hay hash esperado: no se descarga sin poder verificar")

    sess = session or requests
    h = hashlib.sha256()
    total = 0
    try:
        with sess.get(url, stream=True, timeout=HTTP_TIMEOUT) as resp:
            resp.raise_for_status()
            with open(destino, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=CHUNK):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_ASSET_BYTES:
                        raise StagingError(
                            f"el asset supera el tope de {MAX_ASSET_BYTES} bytes")
                    h.update(chunk)
                    fh.write(chunk)
    except StagingError:
        raise
    except Exception as e:
        raise StagingError(f"falló la descarga: {e}")

    if expected_size and total != expected_size:
        raise StagingError(f"tamaño inesperado: {total} != {expected_size}")

    obtenido = h.hexdigest()
    if obtenido.lower() != expected_sha256.lower():
        raise StagingError(
            f"checksum no coincide (esperado {expected_sha256[:12]}…, "
            f"obtenido {obtenido[:12]}…)")

    logger.info("Descarga verificada: %s (%d bytes)", os.path.basename(destino), total)
    return destino


def _es_ruta_segura(nombre, base):
    """
    Evita el clásico agujero de los comprimidos: una entrada llamada
    '../../etc/algo' que al extraer escribe fuera del directorio destino.
    """
    destino = os.path.realpath(os.path.join(base, nombre))
    base_real = os.path.realpath(base)
    return destino == base_real or destino.startswith(base_real + os.sep)


def extract(archivo, destino):
    """Desempaqueta .tar.gz o .zip en `destino`, rechazando rutas que se escapen."""
    os.makedirs(destino, exist_ok=True)

    if archivo.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archivo, "r:gz") as tf:
            for miembro in tf.getmembers():
                if miembro.issym() or miembro.islnk():
                    raise StagingError(f"el paquete trae un link: {miembro.name}")
                if not _es_ruta_segura(miembro.name, destino):
                    raise StagingError(f"ruta insegura en el paquete: {miembro.name}")
            tf.extractall(destino)
    elif archivo.endswith(".zip"):
        with zipfile.ZipFile(archivo) as zf:
            for nombre in zf.namelist():
                if not _es_ruta_segura(nombre, destino):
                    raise StagingError(f"ruta insegura en el paquete: {nombre}")
            zf.extractall(destino)
    else:
        raise StagingError(f"formato de paquete desconocido: {archivo}")
    return destino


def find_binary(raiz, nombre):
    """
    Ubica el ejecutable dentro de lo extraído.

    Los .tar.gz de la CI traen el binario en la raíz, pero se busca en
    profundidad por si algún día se empaqueta dentro de una carpeta.
    """
    directo = os.path.join(raiz, nombre)
    if os.path.isfile(directo):
        return directo
    for base, _dirs, archivos in os.walk(raiz):
        if nombre in archivos:
            return os.path.join(base, nombre)
    raise StagingError(f"no se encontró {nombre} dentro del paquete")


def new_staging(prefijo="fb-update-"):
    """Crea un subdirectorio de staging limpio y devuelve su ruta."""
    return tempfile.mkdtemp(prefix=prefijo, dir=staging_dir())


# Los descargables se borran al terminar cada ciclo, salvo en Android: ahí el
# APK tiene que sobrevivir a la función porque lo lee el instalador del sistema
# después. Si el usuario no acepta la instalación, ese APK (~44 MB) queda
# huérfano y el siguiente chequeo baja otro. Sin esta limpieza, un usuario que
# posterga la actualización llena el teléfono en pocos días.
MAX_STAGING_AGE_SECONDS = 24 * 3600


def cleanup_stale(max_age_seconds=MAX_STAGING_AGE_SECONDS):
    """Borra restos de ciclos anteriores. Devuelve cuántos directorios sacó."""
    import time

    raiz = staging_dir()
    borrados = 0
    ahora = time.time()
    try:
        entradas = os.listdir(raiz)
    except OSError:
        return 0

    for nombre in entradas:
        ruta = os.path.join(raiz, nombre)
        try:
            if not os.path.isdir(ruta):
                continue
            if ahora - os.path.getmtime(ruta) < max_age_seconds:
                continue
            shutil.rmtree(ruta, ignore_errors=True)
            borrados += 1
        except OSError:
            continue

    if borrados:
        logger.info("Limpieza de staging: %d descarga(s) vieja(s) eliminada(s).",
                    borrados)
    return borrados
