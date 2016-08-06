# -*- coding: utf-8 -*-

import socket
from escpos import printer

# TCP_PORT = 9100


class ReceiptDirectJetDriver( printer.Network ):

	def __init__(self, host, port=9100):
		""" escrito aqui solo para tener bien en claro las variables iniciales"""
		return printer.Network.__init__(self,host,port)
