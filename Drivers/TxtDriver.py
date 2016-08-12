# -*- coding: iso-8859-1 -*-

from DriverInterface import DriverInterface

class TxtDriver(DriverInterface):

	def __init__(self, path):
		self.filename = path
		bufsize = 1 # line buffer
		self.file = open(filename, "w", bufsize)

	def sendCommand(self, command, fields, skipStatusErrors=False):
		import random

		message = chr(command)
		if fields:
			message += chr(0x1c)
		message += chr(0x1c).join( fields )
		message += chr(0x03)
		
		print message
		
		self.file.write(message+"\n")

		number = random.randint(2, 12432)
		return [str(number)] * 10

	def close(self):
		self.file.close()