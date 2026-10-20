# coding=utf-8
"""
Respuesta de comandos a la consola de Paxapos.

Hasta ahora el resultado de un comando (getAvailablePrinters, getStatus,
configure, una impresión...) solo quedaba en el log local del dispositivo: ni
MQTT ni Socket.IO devuelven nada al backend. Desde la consola de comandos de
Paxapos (Paxaprinteres > Consola) eso no alcanza: quien manda el comando
necesita ver qué contestó el Fiscalberry.

El backend marca los mensajes que salen de la consola con `cmdId`. Solo esos
se reportan (los trabajos de impresión de todos los días no generan tráfico
extra), con un POST a `{sio_host}/paxaprinter_respuesta.json`, el mismo
servidor y mismo mecanismo que el discover. Es best-effort: corre en un thread
daemon, nunca lanza y nunca demora la impresión.
"""

import json
import threading
import time

import requests

from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.version import VERSION

logger = getLogger()

CLAVE_CMD_ID = "cmdId"
MAX_LARGO_CMD_ID = 64
MAX_LARGO_TEXTO = 2000
# Claves que nunca salen del dispositivo (getActualConfig devuelve el config entero).
_CLAVES_SENSIBLES = ("password", "passwd", "secret", "token", "priv_key", "private_key", "cert")


def cmd_id_de(comando):
    """El cmdId del mensaje si es válido, o None (mensaje que no vino de la consola)."""
    if not isinstance(comando, dict):
        return None
    cmd_id = comando.get(CLAVE_CMD_ID)
    if not isinstance(cmd_id, str) or not cmd_id or len(cmd_id) > MAX_LARGO_CMD_ID:
        return None
    return cmd_id


def sin_metadatos(comando):
    """Copia del comando sin `cmdId`: no es una acción y EscPComandos la tomaría como tal."""
    if not isinstance(comando, dict) or CLAVE_CMD_ID not in comando:
        return comando
    return {k: v for k, v in comando.items() if k != CLAVE_CMD_ID}


def sanitizar(valor, _profundidad=0):
    """Redacta credenciales y recorta textos largos (y estructuras demasiado profundas)."""
    if _profundidad > 8:
        return "..."
    if isinstance(valor, dict):
        limpio = {}
        for k, v in valor.items():
            if any(s in str(k).lower() for s in _CLAVES_SENSIBLES):
                limpio[k] = "***"
            else:
                limpio[k] = sanitizar(v, _profundidad + 1)
        return limpio
    if isinstance(valor, (list, tuple)):
        return [sanitizar(v, _profundidad + 1) for v in list(valor)[:100]]
    if isinstance(valor, (int, float, bool)) or valor is None:
        return valor
    texto = str(valor)
    if len(texto) > MAX_LARGO_TEXTO:
        texto = texto[:MAX_LARGO_TEXTO] + "..."
    return texto


def armar_payload(uuid, cmd_id, comando, resultado, ok, ts=None):
    """Payload del reporte (función pura, testeable sin red)."""
    acciones = []
    if isinstance(comando, dict):
        acciones = [k for k in comando.keys() if k not in (CLAVE_CMD_ID, "jobId")]
    return {
        "uuid": uuid,
        "cmdId": cmd_id,
        "acciones": acciones,
        "ok": bool(ok),
        "resultado": sanitizar(resultado),
        "version": VERSION,
        "ts": ts if ts is not None else int(time.time()),
    }


def _enviar(url, payload, verify):
    try:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        ret = requests.post(url, headers=headers, data=json.dumps(payload, default=str),
                            timeout=15, verify=verify)
        if ret.status_code != requests.codes.ok:
            logger.warning("RESPUESTA:: el servidor contestó %s al reportar el comando %s",
                           ret.status_code, payload.get("cmdId"))
    except Exception as e:
        logger.warning("RESPUESTA:: no se pudo reportar el comando %s: %s", payload.get("cmdId"), e)


def reportar(comando, resultado, ok=True, configberry=None, sincronico=False):
    """Reporta al backend el resultado de un comando que trae `cmdId`.

    No hace nada si el comando no vino de la consola. Nunca lanza.

    Returns:
        bool: True si se disparó el reporte.
    """
    try:
        cmd_id = cmd_id_de(comando)
        if not cmd_id:
            return False
        cfg = configberry or Configberry()
        uuid = cfg.get("SERVIDOR", "uuid", fallback="")
        host = cfg.get("SERVIDOR", "sio_host", fallback="")
        if not uuid or not host:
            logger.warning("RESPUESTA:: falta uuid o sio_host; no se reporta el comando %s", cmd_id)
            return False
        payload = armar_payload(uuid, cmd_id, comando, resultado, ok)
        url = host.rstrip("/") + "/paxaprinter_respuesta.json"
        verify = cfg.get_ssl_verify()
        if sincronico:
            _enviar(url, payload, verify)
        else:
            threading.Thread(target=_enviar, args=(url, payload, verify), daemon=True).start()
        return True
    except Exception as e:
        logger.warning("RESPUESTA:: error armando el reporte: %s", e)
        return False
