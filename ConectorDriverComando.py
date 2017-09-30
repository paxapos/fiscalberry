# -*- coding: iso-8859-1 -*-
from serial import SerialException
import importlib
import threading


class ConectorError(Exception):
    pass


class ConectorDriverComando:
	driver = None

	def __init__(self, comando, driver, *args, **kwargs):
		self._comando = comando
		print("inicializando ConectorDriverComando driver de %s"%driver)

		def init_driver(self, *args):
			# instanciar el driver dinamicamente segun el driver pasado como parametro
			libraryName = "Drivers."+driver+"Driver"
			driverModule = importlib.import_module(libraryName)
			driverClass = getattr(driverModule, driver+"Driver")
			self.driver = driverClass(**kwargs)


		init_driver(self, comando, driver, *args)
		

   	
   	def sendCommand(self, *args):
		return self.driver.sendCommand(*args)


	def close(self):
		self.driver.close()
		self.driver = None
