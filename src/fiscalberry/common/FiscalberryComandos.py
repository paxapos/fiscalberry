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
		"""Reenvía el ticket a otro Fiscalberry.

		Lanza PrinterException si el remoto no responde o no contesta 200: el
		que llama (el spooler) tiene que poder reintentar en vez de dar el
		ticket por impreso.
		"""

		logger.debug(f"Conectando a la URL {host}")
		headers = {'Content-type': 'application/json'}

		try:
			reply = requests.post(host, data=json.dumps(jsonData), headers=headers, timeout=self.timeout)
		except requests.exceptions.Timeout as e:
			# Sin timeout, si NO existe la IP de destino, queda intentando infinitamente.
			logger.error(f"Timeout de conexión con {host} después de {self.timeout} segundos")
			raise PrinterException(f"Timeout con el Fiscalberry {host}") from e
		except requests.exceptions.RequestException as e:
			# Existe la IP destino pero el puerto está cerrado, DNS, etc.
			logger.error(f"No se pudo establecer la conexión con {host}")
			raise PrinterException(f"No se pudo conectar con el Fiscalberry {host}: {e}") from e

		if reply.status_code != 200:
			raise PrinterException(f"El Fiscalberry {host} respondió {reply.status_code}")
		logger.debug("Conexión exitosa")
		return []
