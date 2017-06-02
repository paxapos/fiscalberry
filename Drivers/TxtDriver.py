# -*- coding: iso-8859-1 -*-

from DriverInterface import DriverInterface

class TxtDriver(DriverInterface):

	def __init__(self, path):
		self.filename = path
		bufsize = 1 # line buffer
		self.file = open(self.filename, "w", bufsize)

	def sendCommand(self, command, fields, skipStatusErrors=False):
		import random
		fields = map(lambda x:x.encode("latin-1", 'ignore'), fields)
		message = chr(0x02) + chr( 98 ) + chr(command)
		if fields:
			message += chr(0x1c)
		message += chr(0x1c).join( fields )
		message += chr(0x03)
		checkSum = sum( [ord(x) for x in message ] )
		checkSumHexa = ("0000" + hex(checkSum)[2:])[-4:].upper()
		message += checkSumHexa
		print message
		
		self.file.write(message+"\n")

		number = random.randint(2, 12432)
		return [str(number)] * 10

	def close(self):
		self.file.close()



	def start(self):
		""" iniciar """
		pass

	def end(self):
		pass


	def reconnect(self):
		pass

	def set(self):
		pass