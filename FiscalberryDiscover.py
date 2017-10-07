# -*- coding: utf-8 -*-

import requests
import uuid
import json

def send( configberry ):

	if not configberry.config.has_option('SERVIDOR', "uuid"):
		print uuid.getnode()
		uuidvalue = str(uuid.uuid1(uuid.getnode(),0))[24:]
		configberry.writeSectionWithKwargs('SERVIDOR', {'uuid':uuidvalue})

	senddata = {
		"uuid": configberry.config.get('SERVIDOR', 'uuid'),
		"ip_privada": configberry.config.get('SERVIDOR', 'ip_privada'),
		"raw_data": json.dumps(configberry.getJSON())
	}

	print senddata

	discoverUrl = configberry.config.get('SERVIDOR', "discover_url")

	resp = requests.post(discoverUrl, data=senddata)
	resp.raise_for_status()

	return resp
