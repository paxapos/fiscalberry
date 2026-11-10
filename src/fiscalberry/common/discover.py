import threading
import time
import requests
import json
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.fiscalberry_logger import getLogger 
from fiscalberry.common.printer_detector import listar_impresoras

configberry = Configberry()

def send_discover():
    """
    Envía el discover al servidor para registrar este dispositivo.
    
    Returns:
        bool: True si el discover fue exitoso (servidor respondió 200), False en caso contrario.
    """
    logger = getLogger()
    
    uuidval = configberry.config.get("SERVIDOR", "uuid", fallback="")
    
    if not uuidval:
        logger.error("No se ha configurado el uuid en el archivo de configuracion")
        return False

    data = configberry.getJSON()
    data["installed_printers"] = listar_impresoras()
    senddata = {
        "uuid":  configberry.config.get("SERVIDOR", "uuid"),
        "raw_data": json.dumps(data)
    }

    # Obtener host y construir URL del discover
    host = configberry.config.get("SERVIDOR", "sio_host", fallback="")
    
    if not host:
        logger.debug("No hay sio_host configurado, no tengo el host donde hacer el discover")
        return False

    discoverUrl = host + "/discover.json"
    logger.debug(f"DISCOVER:: URL: {discoverUrl}")

    try:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        ret = requests.post(discoverUrl, headers=headers, data=json.dumps(senddata), timeout=30)

        if ret.status_code == requests.codes.ok:
            logger.debug("DISCOVER:: Registro exitoso en el servidor")
            return True
        else:
            logger.error(f"DISCOVER:: Error - Status: {ret.status_code}, Body: {ret.text[:200]}")
            return False

    except requests.exceptions.Timeout:
        logger.error(f"Timeout al conectar con el Discover en {discoverUrl}")
        return False
    except Exception as e:
        if str(e.args[0]).startswith("Invalid URL"):
            logger.error(f"El formato de 'discover_url' es inválido: \033[91m{discoverUrl}\033[0m")
        logger.error(f"No es posible conectarse con el Discover en {discoverUrl}. El error dice: {str(e)}")
        return False


def send_discover_hasta_registrar(stop_event=None, on_intento_fallido=None, espera_inicial=2, espera_max=30):
    """
    Reintenta el discover hasta que el servidor confirme el registro del dispositivo.

    El link de adopción (QR) solo sirve cuando la Paxaprinter ya existe en el servidor:
    si se abre antes, Paxapos responde "Paxaprinter no encontrada".

    Args:
        stop_event (threading.Event | None): si se activa, deja de reintentar.
        on_intento_fallido (callable | None): se llama con (intento, segundos_hasta_el_proximo)
            después de cada intento fallido.
        espera_inicial (int): segundos antes del primer reintento (se duplica en cada fallo).
        espera_max (int): tope de la espera entre reintentos.

    Returns:
        bool: True cuando el servidor confirmó el registro, False si se detuvo antes.
    """
    logger = getLogger()
    espera = espera_inicial
    intento = 0
    while not (stop_event and stop_event.is_set()):
        intento += 1
        try:
            if send_discover():
                return True
        except Exception as e:
            logger.error(f"DISCOVER:: Error inesperado en el intento {intento}: {e}")
        logger.warning(f"DISCOVER:: Dispositivo sin registrar (intento {intento}), reintento en {espera}s")
        if on_intento_fallido:
            try:
                on_intento_fallido(intento, espera)
            except Exception as e:
                logger.error(f"DISCOVER:: Error en on_intento_fallido: {e}")
        if stop_event:
            if stop_event.wait(espera):
                break
        else:
            time.sleep(espera)
        espera = min(espera * 2, espera_max)
    return False


def send_discover_in_thread():
    thread = threading.Thread(target=send_discover, daemon=True)
    return thread