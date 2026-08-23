"""
Confirmación y reversión automática de una actualización.

El problema: el selftest se corre antes de instalar, pero prueba el binario
aislado. Puede pasar el selftest y aun así no levantar bien en esta máquina
concreta (config vieja, permisos, una impresora que lo cuelga al inicializar).

La solución es el patrón de "confirmación en dos tiempos":

1. Antes de reemplazar el binario se guarda el anterior y se deja una marca.
2. Al arrancar, se cuenta el intento. Si la versión nueva llega a levantar los
   servicios, llama a `confirm()` y la marca desaparece.
3. Si el proceso muere antes de confirmar, systemd (o quien sea) lo reintenta.
   Al superar MAX_BOOTS intentos sin confirmar, se revierte al binario guardado.

Así, un binario que pasa el selftest pero no arranca en el local NO deja al
restaurante sin imprimir: a los pocos segundos vuelve solo a la versión previa.
"""

import json
import os
import time

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("Updater")

# Intentos de arranque antes de dar la versión nueva por perdida. 3 da margen a
# un reinicio ajeno (corte de luz justo después de actualizar) sin quedarse
# eternamente en un binario que no arranca.
MAX_BOOTS = 3

STATE_FILE = "update_pending.json"


def _state_path():
    import platformdirs
    d = platformdirs.user_data_dir("fiscalberry")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, STATE_FILE)


class PendingUpdate:
    def __init__(self, data):
        self.version = data.get("version")
        self.previous_version = data.get("previous_version")
        self.target = data.get("target")
        self.backup = data.get("backup")
        self.boots = int(data.get("boots") or 0)
        self.created_at = data.get("created_at")

    def as_dict(self):
        return {
            "version": self.version,
            "previous_version": self.previous_version,
            "target": self.target,
            "backup": self.backup,
            "boots": self.boots,
            "created_at": self.created_at,
        }

    def backup_exists(self):
        return bool(self.backup) and os.path.isfile(self.backup)

    def __repr__(self):
        return (f"<PendingUpdate {self.previous_version}->{self.version} "
                f"boots={self.boots}>")


def _write(data):
    """Escritura atómica: un corte de luz no puede dejar un JSON a medias."""
    ruta = _state_path()
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)


def read():
    """Devuelve el PendingUpdate vigente, o None."""
    try:
        with open(_state_path(), "r", encoding="utf-8") as fh:
            return PendingUpdate(json.load(fh))
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning(f"Marca de actualización ilegible, se descarta: {e}")
        clear()
        return None


def arm(version, previous_version, target, backup):
    """
    Deja la marca ANTES de reemplazar el binario.

    Se llama antes del swap a propósito: si el proceso muere entre la marca y el
    reemplazo, al arrancar se encuentra una marca cuyo backup es idéntico al
    binario vivo — revertir a eso es inocuo. El orden inverso sí sería peligroso.
    """
    pend = PendingUpdate({
        "version": version,
        "previous_version": previous_version,
        "target": target,
        "backup": backup,
        "boots": 0,
        "created_at": time.time(),
    })
    _write(pend.as_dict())
    logger.info("Actualización armada: %s -> %s (respaldo en %s)",
                previous_version, version, backup)
    return pend


def clear():
    """Borra la marca. No borra el respaldo (de eso se encarga confirm())."""
    try:
        os.remove(_state_path())
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"No se pudo borrar la marca de actualización: {e}")


def register_boot():
    """
    Cuenta este arranque. Devuelve (pendiente, hay_que_revertir).

    Se llama lo antes posible en el arranque, antes de que nada pueda colgarse.
    """
    pend = read()
    if pend is None:
        return None, False

    pend.boots += 1
    _write(pend.as_dict())

    if pend.boots > MAX_BOOTS:
        logger.error(
            "La versión %s no logró confirmar el arranque en %d intentos. "
            "Revirtiendo a %s.", pend.version, MAX_BOOTS, pend.previous_version)
        return pend, True

    logger.info("Arranque %d/%d tras actualizar a %s (sin confirmar todavía)",
                pend.boots, MAX_BOOTS, pend.version)
    return pend, False


def confirm():
    """
    La versión nueva levantó bien: se da por buena y se borra el respaldo.

    Se llama cuando los servicios ya están arriba, no apenas arranca el proceso:
    el punto es justamente distinguir "el binario ejecuta" de "el servicio anda".
    """
    pend = read()
    if pend is None:
        return False

    logger.info("Actualización a %s confirmada.", pend.version)
    if pend.backup and os.path.isfile(pend.backup):
        try:
            os.remove(pend.backup)
        except Exception as e:
            logger.debug(f"No se pudo borrar el respaldo {pend.backup}: {e}")
    clear()
    return True
