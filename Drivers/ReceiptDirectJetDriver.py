# -*- coding: iso-8859-1 -*-

import socket
from escpos import printer

TCP_IP = '127.0.0.1'
TCP_PORT = 9100


from DriverInterface import DriverInterface

class ReceiptDirectJetDriver(DriverInterface):
	printer = None

	def __init__(self, ipnumber):
		self.printer = printer.Network(ipnumber)


		# 0x1D 0xF9 0x35 1
		# colocar en modo ESC P
		self.printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"1")

	def get_printer(self):
		if not self.printer:
			raise Exception('No hay impresora inicializada')
		return self.printer

	def sendCommand(self, command, skipStatusErrors=False):
		print("Command: %d\n" % (command))
		self.printer(command)
		return True
