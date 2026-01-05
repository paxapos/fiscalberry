import threading
import requests
import json
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.fiscalberry_logger import getLogger 
from fiscalberry.common.printer_detector import listar_impresoras

configberry = Configberry()

def send_discover():

    logger = getLogger()
    discoverUrl = False
    
    uuidval = configberry.config.get("SERVIDOR", "uuid", fallback="")
    
    if not uuidval:
        logger.error("No se ha configurado el uuid en el archivo de configuracion")
        return None

    data = configberry.getJSON()
    data["installed_printers"] = listar_impresoras()
    senddata = {
        "uuid":  configberry.config.get("SERVIDOR", "uuid"),
        "raw_data": json.dumps(data)
    }

    ### Enviar al Discover
    host = configberry.config.get("SERVIDOR", "sio_host", fallback="")

    discoverUrl = host + "/discover.json"
    logger.debug(f"DISCOVER:: URL: {discoverUrl}")
    ret = None

    if discoverUrl:
        try:
            headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
            ret = requests.post(discoverUrl, headers=headers, data=json.dumps(senddata))

            if ret.status_code != requests.codes.ok:
                raise Exception(f"Error de conexión con {discoverUrl} status_code: {ret.status_code} - {ret.text}")

        except Exception as e:
            if str(e.args[0]).startswith("Invalid URL"): logger.error(f"El formato de 'discover_url' es inválido: \033[91m{discoverUrl}\033[0m")

            logger.error(f"No es posible conectarse con el Discover en {discoverUrl}. El error dice: {str(e)}")

    else:
        logger.debug("No hay sio_host configurado, no tengo el host donde hacer el discover")

    return None


def send_discover_in_thread():
    thread = threading.Thread(target=send_discover, daemon=True)
    return thread