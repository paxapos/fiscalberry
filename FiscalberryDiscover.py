# -*- coding: utf-8 -*-

import requests
import uuid
import json
import logging



def send(configberry):

    uuid = configberry.config.get('SERVIDOR', 'uuid')

    if not uuid:
        uuid = str(uuid.uuid1(uuid.getnode(), 0))[24:]
        configberry.writeSectionWithKwargs('SERVIDOR', {'uuid': uuid})

    senddata = {
        "uuid": uuid,
        "ip_privada": configberry.config.get('SERVIDOR', 'ip_privada'),
        "raw_data": json.dumps(configberry.getJSON())
    }


    discoverUrl = configberry.config.get('SERVIDOR', "discover_url")

    ret = None
    if discoverUrl:
        try:
            headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
            ret = requests.post(discoverUrl, headers=headers, data=json.dumps(senddata))

            if ret.status_code == requests.codes.ok:

                json_data = json.loads(ret.text)
                paxaprinter = json_data.get("ok").get("Paxaprinter")
            else:
                raise Exception("Error de conexion con "+discoverUrl)
            # antes de comenzar descargo la imagen del barcode
            # barcodeImage = requests.get( , stream=True).raw
        except Exception, e:
            logging.getLogger().info("Mensaje de exception del discover: %s", e)

    return ret
    # resp.raise_for_status()

