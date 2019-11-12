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
		print("viene VIENE viene VIENE al STARTTTT");
		result = self.EpsonLibDriver.OpenPortByName("serial:/dev/ttyS48576348756387")
		print("el result es: ", result)

	def close(self):
		"""Cierra recurso de conexion con impresora"""
		self.EpsonLibDriver.ClosePort();

	def sendCommand(self, jsonData, parameters = None, skipStatusErrors = None):
		"""Envia comando a impresora"""
		pass
		