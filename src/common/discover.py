import threading
import requests
import json
from common.Configberry import Configberry
from common.fiscalberry_logger import getLogger 


configberry = Configberry()

send_once = False
def send_discover():

    global send_once
    
    if send_once:
        return None

    logger = getLogger()
    discoverUrl = False


    senddata = {
        "uuid":  configberry.config.get("SERVIDOR", "uuid"),
        "raw_data": json.dumps(configberry.getJSON())
    }

    ### Enviar al Discover
    host = configberry.config.get("SERVIDOR", "sio_host", fallback="")

    discoverUrl = host + "/discover.json"
    logger.info(f"DISCOVER:: URL: {discoverUrl}")
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
        logger.info("No hay sio_host configurado, no tengo el host donde hacer el discover")

    send_once = True
    
    return None


def send_discover_in_thread():
    thread = threading.Thread(target=send_discover)
    thread.start()
    return thread