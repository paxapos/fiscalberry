# -*- coding: utf-8 -*-


from DriverInterface import DriverInterface
import logging

import requests
import simplejson as json


class JsonDriver(DriverInterface):

	__name__ = "JsonDriver"


	fiscalStatusErrors = []

	printerStatusErrors = []


	def __init__(self, host, user = None, password = None, port=9999):
		logging.getLogger().info("conexion con JSON Driver en host: %s puerto: %s" % (host, port))
		self.host = host
		self.user = user
		self.password = password
		self.port = port

	def start(self):
		"""Inicia recurso de conexion con impresora"""
		raise NotImplementedError

	def close(self):
		"""Cierra recurso de conexion con impresora"""
		raise NotImplementedError

	def sendCommand(self, jsonData, parameters, skipStatusErrors):
		"""Envia comando a impresora"""
		print("asjoasjoajs oajso jaosjajsoj aosj oasoaosjoajsojosa")
		url = "http://%s:%s/fiscal.json" % (self.host, self.port)
		headers = {'Content-type': 'application/json'}

		if self.user and self.password:
			r = requests.post(url, data=json.dumps(jsonData), headers=headers, auth=(self.user, self.password))
		else:
			r = requests.post(url, data=json.dumps(jsonData), headers=headers)
		print(r)
		return r
		

   
