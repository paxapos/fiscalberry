# -*- coding: utf-8 -*-
from DriverInterface import DriverInterface
import logging
from FiscalPrinterDriver import PrinterException


import requests
import json


class FiscalberryDriver(DriverInterface):

	__name__ = "FiscalberryDriver"


	fiscalStatusErrors = []

	printerStatusErrors = []


	def __init__(self, host, printername = "", port=12000, uri = "http", user = None, password = None, after_port = "api", timeout=3):
		logging.getLogger().info("conexion con JSON Driver en uri: %s, host: %s puerto: %s" % (uri, host, port))
		self.host = host
		self.port = port
		self.uri = uri
		self.user = user
		self.password = password
		self.printerName = printername
		self.after_port = after_port
		self.url = "%s://%s:%s/%s" % (uri, host, port, after_port)
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

		logging.getLogger().info("conectando a la URL %s"%url)
		headers = {'Content-type': 'application/json'}

		if self.printerName and jsonData["printerName"]:
			jsonData["printerName"] = self.printerName

		try: 
			if self.password:
				reply = requests.post(url, data=json.dumps(jsonData), headers=headers, auth=(self.user, self.password), timeout=self.timeout)
			else:
				reply = requests.post(url, data=json.dumps(jsonData), headers=headers, timeout=self.timeout)
			print(reply.content)
			
			return reply.content
			
		except requests.exceptions.Timeout as e:			
			# Maybe set up for a retry, or continue in a retry loop
			logging.getLogger().error("timeout de conexion con la impresora fiscal")
		
		except requests.exceptions.RequestException as e:
		    # catastrophic error. bail.
		    logging.getLogger().error(str(e))
		
		

   
