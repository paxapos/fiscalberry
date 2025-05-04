import requests
import json
from fiscalberry.common.fiscalberry_logger import getLogger

class PrinterException(Exception):
	pass

logger = getLogger()

class FiscalberryComandos():
 
	timeout = 5

	DEFAULT_DRIVER = "Fiscalberry"

	def run(self, host, jsonData):
		"""Envia comando a impresora"""

		logger.info(f"Conectando a la URL {host}")
		headers = {'Content-type': 'application/json'}

		try:
			reply = requests.post(host, data=json.dumps(jsonData), headers=headers, timeout=self.timeout)

			if reply.status_code == 200:
				logger.info("Conexión exitosa")
				return []
		except requests.exceptions.Timeout as e:
			# Maybe set up for a retry, or continue in a retry loop
			# Sin timeout, si NO existe la IP de destino, queda intentando infinitamente.
			logger.error(f"Timeout de conexión con {host} después de {self.timeout} segundos")
			return []

		except requests.exceptions.RequestException as e:
			# catastrophic error. bail.
			# Raises en caso de que exista la IP destino pero el puerto esté cerrado
			logger.error(f"No se pudo establecer la conexión con {host}")
			return []
