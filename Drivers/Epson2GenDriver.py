# -*- coding: utf-8 -*-


from DriverInterface import DriverInterface
import logging
from FiscalPrinterDriver import PrinterException
import ctypes
from ctypes import byref, c_int, c_char, c_long, c_short, create_string_buffer
import requests


class Epson2GenDriver(DriverInterface):

	__name__ = "Epson2GenDriver"


	fiscalStatusErrors = []

	printerStatusErrors = []


	def __init__(self, device, port='HTTP'):
		self.device = device
		self.port = port
		self.EpsonLibDriver = ctypes.cdll.LoadLibrary('Comandos/libEpsonFiscalDriver.so')
		self.start()

	def start(self):
		"""Inicia recurso de conexion con impresora"""
		if port == 'serial':
			self.EpsonLibDriver.OpenPortByName('serial:'+device)
		else if port == 'usb':
			self.EpsonLibDriver.OpenPortByName('usb:usb')
		else if port == 'lan':
			self.EpsonLibDriver.OpenPortByName('lan:'+device)

	def close(self):
		"""Cierra recurso de conexion con impresora"""
		self.EpsonLibDriver.ClosePort();

	def sendCommand(self, parameters = None, skipStatusErrors = None):
		"""Envia comando a impresora"""
		self.EpsonLibDriver.sendCommand()
		