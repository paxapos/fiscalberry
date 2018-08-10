# -*- coding: utf-8 -*-

import requests
import uuid
import json
import logging



def send(configberry):
    if not configberry.config.has_option('SERVIDOR', "uuid"):
        uuidvalue = str(uuid.uuid1(uuid.getnode(), 0))[24:]
        configberry.writeSectionWithKwargs('SERVIDOR', {'uuid': uuidvalue})

    senddata = {
        "uuid": configberry.config.get('SERVIDOR', 'uuid'),
        "ip_privada": configberry.config.get('SERVIDOR', 'ip_privada'),
        "raw_data": json.dumps(configberry.getJSON())
    }


    discoverUrl = configberry.config.get('SERVIDOR', "discover_url")

    ret = None
    if discoverUrl:
        try:
            ret = requests.post(discoverUrl, data=senddata)
        except Exception, e:
            logging.getLogger().info("Mensaje de exception del discover: %s", e)

    return ret
    # resp.raise_for_status()

