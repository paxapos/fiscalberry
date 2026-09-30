# coding=utf-8
"""
Identidad del dispositivo: el UUID con el que Paxapos lo reconoce.

Ese UUID es la identidad del equipo (además es el topic MQTT), así que cambiarlo
obliga a re-vincular el comercio y deja huérfana la cola anterior. Vivía solo en
config.ini y se generaba al azar, de modo que desinstalar la app —o borrarle los
datos— creaba un dispositivo nuevo a los ojos del servidor.

En Android se deriva de ANDROID_ID, que es estable para el par
(dispositivo, clave de firma de la app) y sobrevive a desinstalar y reinstalar.
Así, reinstalar devuelve SIEMPRE el mismo UUID. Cambia solo si se restablece el
equipo de fábrica o si se firma la app con otra clave.

En escritorio no hay equivalente confiable, así que se sigue generando al azar
(el config.ini de escritorio no se borra al actualizar).
"""

import logging
import uuid

# Logger de la stdlib a propósito, como en Configberry: este módulo lo importa
# Configberry.resetConfigFile() mientras se crea el config.ini, y
# fiscalberry_logger crea el Configberry al importarse. Importar getLogger de
# ahí cerraba el círculo: en un equipo recién instalado —el primer arranque, sin
# config.ini— el import fallaba, el config.ini quedaba VACÍO y ese proceso
# arrancaba sin uuid ni sio_host (el discover no registraba el equipo y la
# vinculación fallaba). setup_file_logging() configura el logger raíz, así que
# esto igual llega al archivo de log.
logger = logging.getLogger("fiscalberry.DeviceUUID")

# Namespace propio para derivar el UUID: fijo y arbitrario, pero no puede
# cambiar nunca — cambiarlo le daría otra identidad a todos los dispositivos.
FISCALBERRY_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def get_android_id():
    """ANDROID_ID del equipo, o None si no se puede obtener."""
    try:
        from jnius import autoclass

        from fiscalberry.common.android_context import get_android_context

        contexto = get_android_context()
        if contexto is None:
            return None

        Secure = autoclass("android.provider.Settings$Secure")
        android_id = Secure.getString(contexto.getContentResolver(), "android_id")
        return android_id or None
    except Exception as e:
        logger.debug(f"No se pudo leer ANDROID_ID: {e}")
        return None


def generate_device_uuid():
    """
    UUID para un dispositivo que todavía no tiene uno.

    OJO: esto es solo para dispositivos NUEVOS. Si config.ini ya trae un uuid hay
    que respetarlo tal cual, o se rompe la vinculación existente.
    """
    android_id = get_android_id()
    if android_id:
        derivado = str(uuid.uuid5(FISCALBERRY_NAMESPACE, f"fiscalberry:{android_id}"))
        logger.info(f"UUID derivado del identificador del dispositivo: {derivado[:8]}...")
        return derivado

    aleatorio = str(uuid.uuid4())
    logger.info(f"UUID aleatorio (sin identificador de dispositivo): {aleatorio[:8]}...")
    return aleatorio
