# -*- coding: iso-8859-1 -*-
from serial import SerialException
import importlib

class ConectorError(Exception):
    pass


class ConectorDriverComando:
	
	def __init__(self, comando, driver, *args, **kwargs):
		self._comando = comando
		print("inicializando ConectorDriverComando driver de %s"%driver)

		# instanciar el driver dinamicamente segun el driver pasado como parametro
		libraryName = "Drivers."+driver+"Driver"
		print "leyendo la libreria %s"%libraryName
		driverModule = importlib.import_module(libraryName)
		print driverModule
		driverClass = getattr(driverModule, driver+"Driver")
		print driverClass
		self.driver = driverClass(**kwargs)


   	
   	def sendCommand(self, *args):
		return self.driver.sendCommand(*args)


	def close(self):
		self.driver.close()
		self.driver = None
