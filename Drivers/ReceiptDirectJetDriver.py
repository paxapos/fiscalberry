# -*- coding: utf-8 -*-

import socket
from escpos import printer
import threading
import time
# TCP_PORT = 9100


class ReceiptDirectJetDriver( printer.Network ):
	connected = False
	

	def __init__(self, host, port=9100, timeout=10, codepage="cp858"):
		""" escrito aqui solo para tener bien en claro las variables iniciales"""
		self.codepage = codepage

		#default a codepage latino con acentos y eñes
		try:
			printer.Network.__init__(self,host,port, timeout, codepage)	
			self.connected = True
			self.close()
		except Exception:
			self.connected = False

       


	def reconnect(self):
		try:
			self.open()
			self.connected = True
		except Exception as e:
			self.connected = False

