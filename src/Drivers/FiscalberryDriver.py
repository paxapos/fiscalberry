# -*- coding: utf-8 -*-
from DriverInterface import DriverInterface
import logging
import requests
import json

from fiscalberry_logger import getLogger



class FiscalberryDriver(DriverInterface):

	__name__ = "FiscalberryDriver"


	fiscalStatusErrors = []

	printerStatusErrors = []


	def __init__(self, host, printername = "", port=12000, uri = "http", user = None, password = None, after_port = "api", timeout = 5):
		self.logger = getLogger()
		self.logger.info(f"conexion con JSON Driver en uri: {uri}, host: {host} puerto: {port}")
		self.host = host
		self.port = port
		self.uri = uri
		self.user = user
		self.password = password
		self.printerName = printername
		self.after_port = after_port
		self.url = f"{uri}://{host}:{port}/{after_port}"
		self.timeout = int(timeout)

	def start(self):
		"""Inicia recurso de conexion con impresora"""
		pass

	def close(self):
		"""Cierra recurso de conexion con impresora"""
		pass

	def sendCommand(self, jsonData, parameters = None, skipStatusErrors = None):
		"""Envia comando a impresora"""
		url = self.url

		self.logger.info(f"Conectando a la URL {url}")
		headers = {'Content-type': 'application/json'}

		if self.printerName and jsonData["printerName"]:
			jsonData["printerName"] = self.printerName

		try: 
			if self.password:
				reply = requests.post(url, data=json.dumps(jsonData), headers=headers, auth=(self.user, self.password), timeout=self.timeout)
			else:
				reply = requests.post(url, data=json.dumps(jsonData), headers=headers, timeout=self.timeout)
			
			if reply.status_code == 200:
				self.logger.info("Conexión exitosa")
				return []
			
		except requests.exceptions.Timeout as e:			
			# Maybe set up for a retry, or continue in a retry loop
			# Sin timeout, si NO existe la IP de destino, queda intentando infinitamente. 
			self.logger.error(f"Timeout de conexión con {url} después de {self.timeout} segundos")
			return []

		except requests.exceptions.RequestException as e:
		    # catastrophic error. bail.
			# Raises en caso de que exista la IP destino pero el puerto esté cerrado
			self.logger.error(f"No se pudo establecer la conexión con {url}")
			return []