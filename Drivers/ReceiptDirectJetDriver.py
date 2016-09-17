# -*- coding: utf-8 -*-

import socket
from escpos import printer
import threading
import time
# TCP_PORT = 9100


class ReceiptDirectJetDriver( printer.Network ):
	port = 9100
	connected = False
	host = None
	
	def __init__(self, host, port=9100):
		""" escrito aqui solo para tener bien en claro las variables iniciales"""
		self.host = host
		self.port = port
		self.reconectar()
		
					

	def reconectar(self):
		def daemon_keep_alive(self, host,port):
			while not self.connected:
				try:
					printer.Network.__init__(self,host,port)
					self.connected = True
				except Exception as e:
					self.connected = False
					time.sleep( 10 )



		t = threading.Thread(target=daemon_keep_alive, args = (self, selfhost,port))
		t.daemon = True
		t.start()