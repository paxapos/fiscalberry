import threading
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


def send_discover_in_thread():
    thread = threading.Thread(target=send_discover, daemon=True)
    return thread