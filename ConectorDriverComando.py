# -*- coding: iso-8859-1 -*-
from serial import SerialException


class ConectorError(Exception):
    pass


class ConectorDriverComando:
	
	def __init__(self, comando, driverName, *args):
		self._comando = comando

		try:

			if ( driverName == 'Hasar'):
				from Drivers.HasarDriver import HasarDriver
				self.driver = HasarDriver(*args)

			elif (driverName == 'Epson'):
				from Drivers.EpsonDriver import EpsonDriver
				self.driver = EpsonDriver(*args)

			elif (driverName == 'Dummy'):
				from Drivers.DummyDriver import DummyDriver
				self.driver = DummyDriver()

			elif (driverName == 'Txt'):
				from Drivers.TxtDriver import TxtDriver
				self.driver = TxtDriver(args[0])

			elif (driverName == 'File'):
				print args
				from Drivers.FileDriver import FileDriver
				self.driver = FileDriver(args[0])

			else:
				raise ConectorError("No existe el driver", driverName)
		except Exception, e:
		    raise ConectorError("Imposible establecer comunicación.", e)


   	
   	def sendCommand(self, *args):
		return self.driver.sendCommand(*args)


	def close(self):
		self.driver.close()
		self.driver = None
