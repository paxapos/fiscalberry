"""
Candado de instancia única por máquina.

Dos fiscalberry corriendo a la vez en el mismo equipo (servicio viejo + versión
nueva, o servicio + arranque manual) comparten el mismo config.ini y por lo
tanto el mismo uuid: sus clientes MQTT usan el mismo client id, el broker
desconecta al que estaba conectado en cada connect del otro y ambos quedan en
un loop infinito de reconexión mutua (decenas de miles de desconexiones por
hora contra el broker, y la cola de impresión nunca procesa estable).

El candado es un lockfile con flock() en el mismo directorio del config.ini.
flock lo libera el kernel al morir el proceso (aunque sea con kill -9), así
que no hay lockfiles huérfanos que impidan arrancar después de un crash.

En plataformas sin fcntl (Windows, Android) el candado se desactiva en
silencio: es mejor arrancar sin protección que no arrancar.
"""

import os

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger()

try:
    import fcntl
except ImportError:  # Windows / Android: sin flock, candado deshabilitado
    fcntl = None

LOCK_FILE_NAME = "fiscalberry.lock"

# Referencia viva al file object del lock: si se garbage-collectea, el fd se
# cierra y el kernel libera el flock aunque el proceso siga corriendo.
_lock_file = None


def _lock_file_path():
    from fiscalberry.common.Configberry import Configberry
    config_dir = os.path.dirname(Configberry().getConfigFIle())
    return os.path.join(config_dir, LOCK_FILE_NAME)


def acquire_single_instance_lock():
    """
    Intenta tomar el candado de instancia única.

    Si la variable de entorno FISCALBERRY_LOCK_WAIT trae un número de segundos,
    reintenta durante ese lapso en vez de rendirse al primer intento. La usa el
    relanzamiento post-actualización: el proceso viejo todavía puede estar
    muriendo cuando el nuevo arranca, y sin esta espera el reemplazo se pierde
    porque el binario nuevo aborta al no conseguir el candado.

    Returns:
        bool: True si esta instancia puede arrancar (candado tomado, o
              plataforma sin flock). False si YA HAY otra instancia corriendo
              en esta máquina: el llamador debe abortar el arranque.
    """
    global _lock_file
    if fcntl is None:
        logger.debug("single_instance: plataforma sin fcntl, candado deshabilitado")
        return True
    if _lock_file is not None:
        return True

    try:
        espera = float(os.environ.get("FISCALBERRY_LOCK_WAIT") or 0)
    except ValueError:
        espera = 0.0

    path = _lock_file_path()
    try:
        lock_file = open(path, "w")
    except OSError as e:
        # No poder crear el lockfile no debe impedir arrancar.
        logger.warning("single_instance: no se pudo crear %s (%s), candado deshabilitado", path, e)
        return True

    tomado = False
    import time as _time
    limite = _time.monotonic() + espera
    while True:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            tomado = True
            break
        except OSError:
            if _time.monotonic() >= limite:
                break
            logger.debug("single_instance: candado ocupado, reintentando...")
            _time.sleep(0.5)

    if not tomado:
        lock_file.close()
        logger.error(
            "Ya hay otro Fiscalberry corriendo en esta maquina (lock: %s). "
            "Dos instancias con el mismo config.ini pelean por el mismo client id MQTT "
            "y la cola de impresion deja de funcionar. Deteniendo esta instancia; "
            "si queres reiniciar el servicio, para primero el que esta corriendo "
            "(ej: systemctl stop fiscalberry).",
            path,
        )
        return False

    lock_file.truncate(0)
    lock_file.write(str(os.getpid()))
    lock_file.flush()
    _lock_file = lock_file
    logger.debug("single_instance: candado tomado (%s, pid %s)", path, os.getpid())
    return True


def release_single_instance_lock():
    """Libera el candado (también se libera solo al morir el proceso)."""
    global _lock_file
    if _lock_file is not None:
        try:
            if fcntl is not None:
                fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN)
            _lock_file.close()
        except OSError:
            pass
        _lock_file = None
