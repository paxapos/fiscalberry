import requests
import json
from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.print_spooler import PermanentJobError

class PrinterException(Exception):
	pass

logger = getLogger()

class FiscalberryComandos():
 
	# (conexión, respuesta): un remoto lento que ya recibió el ticket no se da por
	# caído, porque el spooler lo reintentaría y el remoto lo imprimiría otra vez.
	timeout = (5, 30)

	DEFAULT_DRIVER = "Fiscalberry"

	def run(self, host, jsonData):
		"""Reenvía el ticket a otro Fiscalberry.

		Lanza PrinterException si no se pudo conectar o el remoto no contesta
		200: el que llama (el spooler) tiene que poder reintentar en vez de dar
		el ticket por impreso. Si el remoto recibió el ticket y no contestó a
		tiempo lanza PermanentJobError: reintentar podría imprimirlo dos veces.
		"""

		logger.debug(f"Conectando a la URL {host}")
		headers = {'Content-type': 'application/json'}

		try:
			reply = requests.post(host, data=json.dumps(jsonData), headers=headers, timeout=self.timeout)
		except requests.exceptions.ReadTimeout as e:
			logger.error(f"Timeout con {host}: {e}")
			raise PermanentJobError(
				f"El Fiscalberry remoto {host} no respondió en {self.timeout[1]} s: puede "
				"haberse impreso; no se reintenta para no duplicarlo") from e
		except requests.exceptions.Timeout as e:
			# Sin timeout, si NO existe la IP de destino, queda intentando infinitamente.
			logger.error(f"Timeout con {host}: {e}")
			raise PrinterException(f"Timeout con el Fiscalberry {host}") from e
		except requests.exceptions.RequestException as e:
			# Existe la IP destino pero el puerto está cerrado, DNS, etc.
			logger.error(f"No se pudo establecer la conexión con {host}")
			raise PrinterException(f"No se pudo conectar con el Fiscalberry {host}: {e}") from e

		if reply.status_code != 200:
			raise PrinterException(f"El Fiscalberry {host} respondió {reply.status_code}")
		logger.debug("Conexión exitosa")
		return []
