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
			print(kwargs)
			self.driver = driverClass(**kwargs)


		t = threading.Thread(target=init_driver, args = (self, comando, driver, args))
		t.daemon = True
		t.start()

   	
   	def sendCommand(self, *args):
		return self.driver.sendCommand(*args)


	def close(self):
		self.driver.close()
		self.driver = None
