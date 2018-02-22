# -*- coding: utf-8 -*-


from JsonDriver import JsonDriver
from dicttoxml import dicttoxml



class XmlDriver(JsonDriver):

	__name__ = "XmlDriver"

	def sendCommand(self, jsonData, parameters = None, skipStatusErrors = None):
		"""Envia comando a impresora"""
		url = "http://%s:%s/fiscal.xml" % (self.host, self.port)

		logging.getLogger().info("conectando a la URL %s"%url)
		headers = {'Content-type': 'text/xml'}

		xml = dicttoxml(some_dict)
		xmlData = dicttoxml(jsonData)
		print(xmlData)

		try: 
			if self.password:
				r = requests.post(url, data=xmlData, headers=headers, auth=(self.user, self.password))
			else:
				r = requests.post(url, data=xmlData, headers=headers)
			print("INICIANDO DRIVER XMLLLLLL::::")
			print(r)
			print(r.content)
			print("salio la respuesta")
			
			return r
			
		except requests.exceptions.Timeout:			
		    # Maybe set up for a retry, or continue in a retry loop
		    logging.getLogger().error("titeout de conexion con la fiscal")
		except requests.exceptions.RequestException as e:
		    # catastrophic error. bail.
		    logging.getLogger().error(str(e))
		
		