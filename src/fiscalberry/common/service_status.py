# coding=utf-8
"""
Estado del servicio compartido entre procesos, vía archivo.

En Android la UI (Activity) y el servicio de impresión corren en procesos
Android DISTINTOS: la UI no puede ver los objetos del servicio, así que no tiene
forma de saber si SocketIO/MQTT están realmente conectados. Antes la UI miraba
su propio ServiceController — que en Android nunca conecta nada — y mostraba
cualquier cosa.

El servicio escribe acá su estado cada pocos segundos y la UI lo lee. Se usa el
directorio de config, que ambos procesos comparten (misma app, mismo UID).

El estado se considera VENCIDO si nadie lo actualizó hace más de
STATUS_MAX_AGE_SECONDS: un archivo viejo significa servicio caído, no conectado.
"""

import json
import os
import tempfile
import time

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("ServiceStatus")

STATUS_FILE_NAME = "service_status.json"
# Ventana de gracia: el servicio escribe cada ~5s, así que 20s tolera un par de
# ciclos perdidos (GC, Doze) sin reportar "caído" en falso.
STATUS_MAX_AGE_SECONDS = 20


def _status_file_path():
    from fiscalberry.common.Configberry import Configberry

    config_dir = os.path.dirname(Configberry().getConfigFIle())
    return os.path.join(config_dir, STATUS_FILE_NAME)


def write_status(sio_connected, mqtt_connected, extra=None):
    """
    Publica el estado actual. Nunca lanza: es telemetría, no puede tumbar el
    servicio de impresión.
    """
    payload = {
        "ts": time.time(),
        "pid": os.getpid(),
        "sio_connected": bool(sio_connected),
        "mqtt_connected": bool(mqtt_connected),
    }
    if extra:
        payload.update(extra)

    try:
        path = _status_file_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Escritura atómica: la UI lee en paralelo y no debe ver JSON a medias.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".status-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception as e:
        logger.debug(f"No se pudo escribir el estado del servicio: {e}")


def read_status(max_age_seconds=STATUS_MAX_AGE_SECONDS):
    """
    Devuelve el estado publicado por el servicio, o None si no hay o venció.
    None significa "no sé / servicio caído", nunca se asume conectado.
    """
    try:
        with open(_status_file_path(), "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (FileNotFoundError, ValueError):
        return None
    except Exception as e:
        logger.debug(f"No se pudo leer el estado del servicio: {e}")
        return None

    ts = payload.get("ts")
    if not isinstance(ts, (int, float)):
        return None
    if max_age_seconds is not None and (time.time() - ts) > max_age_seconds:
        return None
    return payload


def clear_status():
    """Borra el estado (al detener el servicio: no dejar un estado mentiroso)."""
    try:
        os.unlink(_status_file_path())
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"No se pudo borrar el estado del servicio: {e}")
