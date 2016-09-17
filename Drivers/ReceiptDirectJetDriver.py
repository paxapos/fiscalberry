# -*- coding: utf-8 -*-

import socket
from escpos import printer
import threading
import time
# TCP_PORT = 9100


class ReceiptDirectJetDriver( printer.Network ):
	connected = False
	
	def __init__(self, host, port=9100, timeout=10):
		""" escrito aqui solo para tener bien en claro las variables iniciales"""
		try:
			printer.Network.__init__(self,host,port, timeout)	
			self.connected = True
		except Exception:
			self.connected = False


	def reconnect(self):
		try:
			self.open()
			self.connected = True
		except Exception as e:
			self.connected = False
