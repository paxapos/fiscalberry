# -*- coding: utf-8 -*-

from datetime import datetime
from DriverInterface import DriverInterface
import logging
from FiscalPrinterDriver import PrinterException
import ctypes
from ctypes import byref, c_int, c_char, c_char_p, c_long, c_short, create_string_buffer
import requests
import platform
import os


archbits = platform.architecture()[0]
newpath  = os.path.dirname(os.path.realpath(__file__))
if archbits[0:2] == "64":
	fullpath = "/lib64/libEpsonFiscalInterface.so"
else:
	fullpath = "/lib/libEpsonFiscalInterface.so"

EpsonLibInterface = ctypes.cdll.LoadLibrary(fullpath)


class Epson2GenDriver(DriverInterface):

	__name__ = "Epson2GenDriver"


	fiscalStatusErrors = []

	printerStatusErrors = []


	#
	#	path disponibles
	#	default serial: /dev/usb/lp0
	#	“0” – USB.
	#	“1” – COM1 o ttyS0.
	#	“2” – COM2 o ttyS1.
	#	“ x ” – COM x o ttyS( x -1).
	#	“serial:COM x ” – COM x
	#	“serial: /dev/ttyS x ” – ttyS x
	#	“lan:192.168.1.1” – Http ip 192.168.1.1
	#	“lan:192.168.1.1:443” – Http ip 192.168.1.1 puerto 443
	#
	def __init__(self, path='serial: /dev/usb/lp0', baudrate=9600):
		print "-"*25
		print "*"*25
		print "   EPSON FISCAL"
		print "*"*25
		print "-"*25

		self.port = path
		self.baudrate = baudrate
		self.EpsonLibInterface = EpsonLibInterface


	def start(self):
		"""Inicia recurso de conexion con impresora"""
		self.EpsonLibInterface.ConfigurarVelocidad( c_int(self.baudrate).value )
		self.EpsonLibInterface.ConfigurarPuerto( self.port )
		self.EpsonLibInterface.Conectar()

		
		str_version_max_len = 500
		str_version = create_string_buffer( b'\000' * str_version_max_len )
		int_major = c_int()
		int_minor = c_int()

		error = self.EpsonLibInterface.ConsultarVersionEquipo( str_version, c_int(str_version_max_len).value, byref(int_major), byref(int_minor) )
		print "Machinne Version        : ",
		print error
		print "String Machinne Version : ",
		print str_version.value
		print "Major Machinne Version  : ",
		print int_major.value
		print "Minor Machine Version   : ",
		print int_minor.value


		# status
		error = self.EpsonLibInterface.ConsultarEstadoDeConexion()
		print "Conexion Status         : ",
		print error

		error = self.EpsonLibInterface.ComenzarLog()
		print "Log iniciado Status         : ",
		print error

		logging.getLogger().info("Conectada la Epson 2Gen al puerto  : %s" % (self.port) )

	def close(self):
		"""Cierra recurso de conexion con impresora"""

		# get last error
		error = self.EpsonLibInterface.ConsultarUltimoError()
		print "Last Error            : ",
		print error

		
		self.EpsonLibInterface.Desconectar();
		logging.getLogger().info("DESConectada la Epson 2Gen al puerto: %s" % (self.port) )

	def ObtenerEstadoFiscal(self):
		return self.EpsonLibInterface.ObtenerEstadoFiscal()

	def sendCommand(self, commandNumber, fields, skipStatusErrors=False):
		pass

	def ImprimirAuditoria( desde, hasta, id_modificador = 500):
		"""

		id_modificador 		integer
		• 500 – Auditoría detallada.
		• 501 – Auditoría resumida.
		
		Número o fecha del cierre Z inicial.
		desde string
		• Formato para número de Cierre Z: “9999”
		• Formato para fecha: “ddmmyy”
		
		Número o fecha del cierre Z final. (inclusive)
		hasta string
		• Formato para número de Cierre Z: “9999”
		• Formato para fecha: “ddmmyy”

		"""
    
		return self.EpsonLibInterface.ImprimirAuditoria( id_modificador, desde, hasta )

	def cargarAjuste(self, description, amount, ivaid, negative):
		"""
		Integer CargarAjuste( 
			Integer id_modificador, 
				• 400 – Descuento.
				• 401 – Ajuste.
				• 402 – Ajuste negativo.
			String descripcion,
			String monto,  “nnnnnnnnnn.nn”. (10,2)
			int id_tasa
			String codigo_interno

		"""
		amount 		= "%.2f" % float(amount)
		id_modificador = 400
		if negative:
			id_modificador = 401
		return self.EpsonLibInterface.CargarAjuste(id_modificador, description, str(amount), ivaid, "")

	def ImprimirItem(self, id_modificador, description, qty, precio, id_tasa_iva, ii_id = 0, ii_valor = "0.0", id_codigo = 1, codigo= "1", codigo_unidad_matrix = "1", codigo_unidad_medida = 7):
		"""Integer ImprimirItem( 
				Integer id_modificador, 
				String descripcion,
				String cantidad, 
				String precio, 
				Integer id_tasa_iva,
				Integer ii_id, 
				String ii_valor, header
				Integer id_codigo,
				String codigo, 
				String codigo_unidad_matrix,
				Integer codigo_unidad_medida )
		"""
		description = c_char_p(description).value
		qty 		= qty
		precio 		= str(precio)
		id_tasa_iva = id_tasa_iva



		print " OoO "*25
		print "imprime item modif %s - dec: %s qty: %s - precio %s - Iva %s " % (id_modificador, description, qty, precio, id_tasa_iva)


		return self.EpsonLibInterface.ImprimirItem(id_modificador, description, qty, precio, id_tasa_iva,ii_id,ii_valor,id_codigo,codigo,codigo_unidad_matrix,codigo_unidad_medida)