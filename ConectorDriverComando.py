# -*- coding: iso-8859-1 -*-
from serial import SerialException
import importlib

class ConectorError(Exception):
    pass


class ConectorDriverComando:
	
	def __init__(self, comando, driver, *args, **kwargs):
		self._comando = comando
		print("inicializando conectir driver de %s"%driver)

		# instanciar el driver dinamicamente segun el driver pasado como parametro
		libraryName = "Drivers."+driver+"Driver"
		driverModule = importlib.import_module(libraryName)
		driverClass = getattr(driverModule, driver+"Driver")
		self.driver = driverClass(**kwargs)


   	
   	def sendCommand(self, *args):
		return self.driver.sendCommand(*args)


	def close(self):
		self.driver.close()
		self.driver = None
