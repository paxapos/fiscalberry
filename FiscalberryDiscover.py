# -*- coding: utf-8 -*-
import requests
import uuid
import json
import logging

def send(configberry):

    logger = logging.getLogger("Fb => Discover")
    uuidFb = False
    discoverUrl = False

    ### Crear el UUID
    uuidFb = configberry.config.get('SERVIDOR', 'uuid')

    if not uuidFb:
        uuidFb = str(uuid.uuid1(uuid.getnode(), 0))[24:]
        configberry.writeSectionWithKwargs('SERVIDOR', {'uuid': uuidFb})
        logger.info(f"Se estableció la siguente \033[1mUUID: \033[92m{uuidFb}\033[0m")

    senddata = {
        "uuid": uuidFb,
        "ip_privada": configberry.config.get('SERVIDOR', 'ip_privada'),
        "raw_data": json.dumps(configberry.getJSON())
    }

    ### Enviar al Discover
    discoverUrl = configberry.config.get('SERVIDOR', "discover_url")

    ret = None

    if discoverUrl:
        try:
            headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
            ret = requests.post(discoverUrl, headers=headers, data=json.dumps(senddata))

            if ret.status_code == requests.codes.ok:
                json_data = json.loads(ret.text)
                _ = json_data.get("ok").get("Paxaprinter")

            else:
                raise Exception(f"Error de conexión con {discoverUrl}")

        except Exception as e:
            if str(e.args[0]).startswith("Invalid URL"): logger.error(f"El formato de 'discover_url' es inválido: \033[91m{discoverUrl}\033[0m")
            else: logger.error("No es posible conectarse con el Discover")
            

    else:
        logger.info("No hay Discover configurado")

    return None
