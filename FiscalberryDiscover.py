import requests
import uuid

import socket
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP



def send(discoverUrl):
	print uuid.getnode()
	uuidvalue = str(uuid.uuid1(uuid.getnode(),0))[24:]

	ip = get_ip()

	senddata = {
		'uuid': uuidvalue,
		'ip_private': ip
	}

	resp = requests.post(discoverUrl, data=senddata)
	print senddata
	print resp
	return resp
