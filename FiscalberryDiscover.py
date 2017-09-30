import requests
import uuid


def send( configberry ):

	if not configberry.config.has_option('SERVIDOR', "uuid"):
		print uuid.getnode()
		uuidvalue = str(uuid.uuid1(uuid.getnode(),0))[24:]
		configberry.writeSectionWithKwargs('SERVIDOR', {'uuid':uuidvalue})

	senddata = {
		"uuid": configberry.config.get('SERVIDOR', 'uuid'),
		"ip_privada": configberry.config.get('SERVIDOR', 'ip_privada')
	}

	discoverUrl = configberry.config.get('SERVIDOR', "discover_url")

	resp = requests.post(discoverUrl, data=senddata)
	print senddata
	print resp
	return resp
