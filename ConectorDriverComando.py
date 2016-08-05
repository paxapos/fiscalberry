# -*- coding: iso-8859-1 -*-
from serial import SerialException
import importlib

class ConectorError(Exception):
    pass


class ConectorDriverComando:
	
	def __init__(self, comando, driverName, *args, **kwargs):
		self._comando = comando
		print("inicializando conectir driver")

		# instanciar el driver dinamicamente segun el driverName pasado como parametro
		libraryName = "Drivers."+driverName+"Driver"
		driverModule = importlib.import_module(libraryName)
		driverClass = getattr(driverModule, driverName+"Driver")
		self.driver = driverClass(*args)


   	
   	def sendCommand(self, *args):
		return self.driver.sendCommand(*args)


	def close(self):
		self.driver.close()
		self.driver = None
