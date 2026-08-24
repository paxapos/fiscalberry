import threading
import requests
import json
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.printer_detector import listar_impresoras
from fiscalberry.version import VERSION

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

    # Detectar impresoras NO puede impedir que el dispositivo se registre.
    #
    # Esto corría fuera del try y era obligatorio para armar el payload: si
    # `listar_impresoras()` fallaba —en Android escanea USB y Bluetooth, que
    # dependen de permisos que el usuario todavía no otorgó— el discover ni se
    # intentaba. Resultado: el dispositivo nunca quedaba registrado y la
    # vinculación moría con "Paxaprinter no encontrada", sin ninguna pista de
    # que el problema eran las impresoras.
    #
    # Además, en la primera vinculación NO HAY impresoras configuradas: es
    # justo el momento en que esa lista viene vacía. Que sea un requisito para
    # registrarse es al revés de como tiene que ser.
    try:
        data = configberry.getJSON()
    except Exception as e:
        logger.error(f"DISCOVER:: no se pudo leer la configuración ({e}); "
                     "se envía el registro igual.")
        data = {}

    try:
        data["installed_printers"] = listar_impresoras()
    except Exception as e:
        logger.error(f"DISCOVER:: falló la detección de impresoras ({e}); "
                     "se registra el dispositivo sin lista de impresoras.")
        data["installed_printers"] = []

    senddata = {
        "uuid": uuidval,
        # Version del cliente: el backend la persiste y decide capacidades
        # (ej. mandar trabajos 'printRaw' solo a clientes que los soportan).
        "version": VERSION,
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
        verify = configberry.get_ssl_verify()
        if verify is False:
            # Silenciar el warning de urllib3 cuando se desactiva verificación a propósito (dev)
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass
        ret = requests.post(discoverUrl, headers=headers, data=json.dumps(senddata), timeout=30, verify=verify)

        if ret.status_code == requests.codes.ok:
            logger.info("DISCOVER:: Registro exitoso en el servidor")
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