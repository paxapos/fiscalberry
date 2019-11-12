# -*- coding: iso-8859-1 -*-
import string
import types
import logging
import ctypes
import unicodedata
from ctypes import byref, c_int, c_char, c_long, c_short, create_string_buffer
from Comandos.ComandoFiscalInterface import ComandoFiscalInterface
from Drivers.FiscalPrinterDriver import PrinterException
from ComandoInterface import formatText

EpsonLibInterface = ctypes.cdll.LoadLibrary('Comandos/libEpsonFiscalInterface.so')


class Epson2GenComandos(ComandoFiscalInterface):
	# el traductor puede ser: TraductorFiscal o TraductorReceipt
	# path al modulo de traductor que este comando necesita
	traductorModule = "Traductores.TraductorFiscal"

	DEFAULT_DRIVER = "Json"

	
	AVAILABLE_MODELS = ["TM-T900"]


	docTypeNames = {
		"DOC_TYPE_CUIT": "CUIT",
		"DOC_TYPE_LIBRETA_ENROLAMIENTO": 'L.E.',
		"DOC_TYPE_LIBRETA_CIVICA": 'L.C.',
		"DOC_TYPE_DNI": 'DNI',
		"DOC_TYPE_PASAPORTE": 'PASAP',
		"DOC_TYPE_CEDULA": 'CED',
		"DOC_TYPE_SIN_CALIFICADOR": 'S/C'
	}

	docTypes = {
		"CUIT": 'TipoCUIT',
		"CUIL": 'TipoCUIL',
		"LIBRETA_ENROLAMIENTO": 'TipoLE',
		"LIBRETA_CIVICA": 'TipoLC',
		"DNI": 'TipoDNI',
		"PASAPORTE": 'TipoPasaporte',
		"CEDULA": 'TipoCI',
		"SIN_CALIFICADOR": ' ',
	}


	ivaTypes = {
		"RESPONSABLE_INSCRIPTO": 'ResponsableInscripto',
		"EXENTO": 'ResponsableExento',
		"NO_RESPONSABLE": 'NoResponsable',
		"CONSUMIDOR_FINAL": 'ConsumidorFinal',
		"NO_CATEGORIZADO": 'NoCategorizado',
		"RESPONSABLE_MONOTRIBUTO": 'Monotributo',
		"MONOTRIBUTISTA_SOCIAL": 'MonotributoSocial',
		"PEQUENIO_CONTRIBUYENTE_EVENTUAL": 'Eventual',
		"PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL": 'EventualSocial',
	}

	comprobanteTypes = {
		"T": 1,
		"FB": 2,
		"FA": 2,
		"FC": 2,
		"FM": 2,
		"NCT": 3,
		"NCA": 3,
		"NCB": 3,
		"NCC": 3,
		"NCM": 3,
		"NDA": 4,
		"NDB": 4,
		"NDC": 4,
		"NDM": 4,
	}

	def getStatus(self, *args):
		pass

		#self.conector.sendCommand( jdata )

	def setTrailer(self, trailer=None):
		"""Establecer pie"""
		pass

	def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
		pass


	def _setCustomerData(self, name=" ", address=" ", doc=" ", docType=" ", ivaType="T"):
		pass
		#self.conector.sendCommand( jdata )

	# Documentos no fiscales

	def openNonFiscalReceipt(self):
		"""Abre documento no fiscal"""
		pass

	def printFiscalText(self, text):
		pass
		#self.conector.sendCommand( jdata )

	def printNonFiscalText(self, text):
		"""Imprime texto fiscal. Si supera el límite de la linea se trunca."""
		pass
		#self.conector.sendCommand( jdata )

	def closeDocument(self, copias = 0, email = None):
		"""Cierra el documento que esté abierto"""
		pass

		#return self.conector.sendCommand( jdata )


	def cancelDocument(self):
		"""Cancela el documento que esté abierto"""
		pass
		#return self.conector.sendCommand( jdata )

	def addItem(self, description, quantity, price, iva, itemNegative = False, discount=0, discountDescription='', discountNegative=False):
		"""Agrega un item a la FC.
			@param description          Descripción del item. Puede ser un string o una lista.
				Si es una lista cada valor va en una línea.
			@param quantity             Cantidad
			@param price                Precio (incluye el iva si la FC es B o C, si es A no lo incluye)
			@param iva                  Porcentaje de iva
			@param itemNegative         Sin efecto en 2GEN, se agrega este parametro para respetar la interfaz del TraductorFiscal
			@param discount             Importe de descuento
			@param discountDescription  Descripción del descuento
			@param discountNegative     True->Resta de la FC
		"""

		return True

	def addPayment(self, description, payment):
		"""Agrega un pago a la FC.
			@param description  Descripción
			@param payment      Importe
		"""
		pass

		#self.conector.sendCommand( jdata )

	
	def __openTicket(self, tipoComprobante):
	
		return self.conector.sendCommand( 1 )


	# Ticket fiscal (siempre es a consumidor final, no permite datos del cliente)

	def openTicket(self, comprobanteType = "T"):
		"""Abre documento fiscal"""
		return self.__openTicket( comprobanteType )

	def openBillTicket(self, type, name, address, doc, docType, ivaType):
		"""
		Abre un ticket-factura
			@param  type        Tipo de Factura "A", "B", o "C"
			@param  name        Nombre del cliente
			@param  address     Domicilio
			@param  doc         Documento del cliente según docType
			@param  docType     Tipo de documento
			@param  ivaType     Tipo de IVA
		"""
		pass
		

	def openBillCreditTicket(self, type, name, address, doc, docType, ivaType, reference="NC"):
		"""
		Abre un ticket-NC
			@param  type        Tipo de Factura "A", "B", o "C"
			@param  name        Nombre del cliente
			@param  address     Domicilio
			@param  doc         Documento del cliente según docType
			@param  docType     Tipo de documento
			@param  ivaType     Tipo de IVA
			@param  reference
		"""
		pass

	def __cargarNumReferencia(self, numero):
		pass

	def openDebitNoteTicket(self, type, name, address, doc, docType, ivaType):
		"""
		Abre una Nota de Débito
			@param  type        Tipo de Factura "A", "B", o "C"
			@param  name        Nombre del cliente
			@param  address     Domicilio
			@param  doc         Documento del cliente según docType
			@param  docType     Tipo de documento
			@param  ivaType     Tipo de IVA
			@param  reference
		"""
		pass

	def openRemit(self, name, address, doc, docType, ivaType):
		"""
		Abre un remito
			@param  name        Nombre del cliente
			@param  address     Domicilio
			@param  doc         Documento del cliente según docType
			@param  docType     Tipo de documento
			@param  ivaType     Tipo de IVA
		"""
		pass

	def openReceipt(self, name, address, doc, docType, ivaType, number):
		"""
		Abre un recibo
			@param  name        Nombre del cliente
			@param  address     Domicilio
			@param  doc         Documento del cliente según docType
			@param  docType     Tipo de documento
			@param  ivaType     Tipo de IVA
			@param  number      Número de identificación del recibo (arbitrario)
		"""
		pass

	def addRemitItem(self, description, quantity):
		"""Agrega un item al remito
			@param description  Descripción
			@param quantity     Cantidad
		"""
		pass

	def addReceiptDetail(self, descriptions, amount):
		"""Agrega el detalle del recibo
			@param descriptions Lista de descripciones (lineas)
			@param amount       Importe total del recibo
		"""
		pass

	def ImprimirAnticipoBonificacionEnvases(self, description, amount, iva, negative=False):
		"""Agrega un descuento general a la Factura o Ticket.
			@param description  Descripción
			@param amount       Importe (sin iva en FC A, sino con IVA)
			@param iva          Porcentaje de Iva
			@param negative     Si negative = True, se añadira el monto como descuento, sino, sera un recargo
		"""
		pass

	def addAdditional(self, description, amount, iva, negative=False):
		"""Agrega un descuento general a la Factura o Ticket.
			@param description  Descripción
			@param amount       Importe (sin iva en FC A, sino con IVA)
			@param iva          Porcentaje de Iva
			@param negative     Si negative = True, se añadira el monto como descuento, sino, sera un recargo
		"""
		pass
		

	def setCodigoBarras(self, numero , tipoCodigo = "CodigoTipoI2OF5", imprimeNumero =  "ImprimeNumerosCodigo" ):
		pass

	def getLastNumber(self, letter):
		"""Obtiene el último número de FC"""
		pass

	def getLastCreditNoteNumber(self, letter):
		"""Obtiene el último número de FC"""
		pass

	def getLastRemitNumber(self):
		"""Obtiene el último número de Remtio"""
		pass

	def cancelAnyDocument(self):
		"""Este comando no esta disponible en la 2da generación de impresoras, es necesaria su declaración por el uso del TraductorFiscal """
		return self.cancelDocument()

	def dailyClose(self, type):
		pass


	def getWarnings(self):
		return []

	def openDrawer(self):
		pass
