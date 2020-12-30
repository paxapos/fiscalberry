# -*- coding: iso-8859-1 -*-
import string
import types
import logging
import unicodedata
import json
from Comandos.ComandoFiscalInterface import ComandoFiscalInterface
from Drivers.FiscalPrinterDriver import PrinterException
from ComandoInterface import formatText
from collections import OrderedDict


class Sam4s2GenComandos(ComandoFiscalInterface):
	# el traductor puede ser: TraductorFiscal o TraductorReceipt
	# path al modulo de traductor que este comando necesita
	traductorModule = "Traductores.TraductorFiscal"

	DEFAULT_DRIVER = "Json"

	
	AVAILABLE_MODELS = ["ellix-40F"]

	CMD_OPEN_FISCAL_RECEIPT = '40'
	CMD_OPEN_BILL_TICKET = '60'

	CMD_OPEN_CREDIT_NOTE = '80'

	CMD_PRINT_TEXT_IN_FISCAL = '41'
	CMD_PRINT_LINE_ITEM = '42'
	CMD_PRINT_SUBTOTAL = '43'
	CMD_ADD_PAYMENT = '44'
	CMD_CLOSE_FISCAL_RECEIPT = '45'
	CMD_DAILY_CLOSE = '39'
	CMD_STATUS_REQUEST = '2a'

	CMD_CLOSE_CREDIT_NOTE = '81'

	CMD_CREDIT_NOTE_REFERENCE = '93'

	CMD_LAST_ITEM_DISCOUNT = '55'
	CMD_GENERAL_DISCOUNT = '54'

	CMD_OPEN_NON_FISCAL_RECEIPT = '48'
	CMD_PRINT_NON_FISCAL_TEXT = '49'
	CMD_CLOSE_NON_FISCAL_RECEIPT = '4a'

	CMD_CANCEL_ANY_DOCUMENT = '98'

	CMD_OPEN_DRAWER = '7b'

	CMD_SET_HEADER_TRAILER = '5d'

	# Documentos no fiscales homologados (remitos, recibos, etc.)
	CMD_OPEN_DNFH = '80'
	CMD_PRINT_EMBARK_ITEM = '82'
	CMD_PRINT_ACCOUNT_ITEM = '83'
	CMD_PRINT_QUOTATION_ITEM = '84'
	CMD_PRINT_DNFH_INFO = '85'
	CMD_PRINT_RECEIPT_TEXT = '97'
	CMD_CLOSE_DNFH = '81'

	CMD_REPRINT = '99'

	docTypes = {
        "CUIT": '80',
        "LIBRETA_ENROLAMIENTO": '89',
        "LIBRETA_CIVICA": '90',
        "DNI": '96',
        "PASAPORTE": '94',
        "CEDULA": '91',
        "SIN_CALIFICADOR": '99',
	}


	ivaTypes = {
        "RESPONSABLE_INSCRIPTO": 'I',
        "NO_RESPONSABLE": 'N',
        "EXENTO": 'E',
        "CONSUMIDOR_FINAL": 'F',
        "RESPONSABLE_MONOTRIBUTO": 'M',
        "RESPONSABLE_NO_INSCRIPTO_BIENES_DE_USO": 'B',
        "MONOTRIBUTISTA_SOCIAL": 'S',
        "PEQUENIO_CONTRIBUYENTE_EVENTUAL": 'C',
        "PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL": 'V',
    }

	esFacturaA = False

    def start(self):
        pass

    def close(self):
        pass

	def getStatus(self, *args):
		jdata = OrderedDict()
		jdata['cmd'] = self.CMD_STATUS_REQUEST
		jdata['field'] = []

		return self._sendCommand( jdata )

	def setTrailer(self, trailer=None):
		"""Establecer pie"""
		pass

	def _sendCommand(self, jsonData):
		jsonData = {
		    "ifprote": {
		        "packet": [
		            jsonData
		        ]
		    }
		}
		try:
			result = self.conector.sendCommand(jsonData)
			return result
		except PrinterException, e:
			logging.getLogger().error("PrinterException: %s" % str(e))
    		raise Exception("Error de la impresora fiscal: %s.\nComando enviado: %s" % \
                           		(str(e), commandString))

	# Documentos no fiscales

	def openNonFiscalReceipt(self):
		"""Abre documento no fiscal"""
		pass

	def printFiscalText(self, text):
		pass

	def printNonFiscalText(self, text):
		pass

	def closeDocument(self):
		"""Cierra el documento que esté abierto"""
		jdata = OrderedDict()
		jdata['cmd'] = self.CMD_CLOSE_FISCAL_RECEIPT
		jdata['field'] = []

		return self._sendCommand( jdata )


	def cancelDocument(self):
		"""Cancela el documento que esté abierto"""
		jdata = OrderedDict()
		jdata['cmd'] = self.CMD_ADD_PAYMENT
		jdata['field'] = ['', 0, 'C']

		return self._sendCommand( jdata )

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
		jdata = OrderedDict()
		jdata['cmd'] = self.CMD_PRINT_LINE_ITEM
		jdata['field'] = [
							description, #nombre del item
							quantity, #cantidad
							price, #precio unitario
							iva, #alícuota IVA
							"M", #tipo de operación: M (Venta)
							0, #tasa de ajuste (impuesto interno porcentual)
							0, #monto impuesto interno fijo
							"", #código producto
							"", #código matrix
							0,
							0, #Unidad de Medida, 0 = SIN DESCRIPCIÓN
							1, #cantidad de unidades que contiene el producto
							'T', #Los montos enviados son los que deben imprimirse
						]

		return self._sendCommand(jdata)

	def addPayment(self, description, payment):
		"""Agrega un pago a la FC.
			@param description  Descripción
			@param payment      Importe
		"""
		jdata = OrderedDict()
		jdata['cmd'] = self.CMD_ADD_PAYMENT
		jdata['field'] = [
						description,
						payment,
						8, #Efectivo
						] 

		self._sendCommand( jdata )

	
	# Ticket fiscal (siempre es a consumidor final, no permite datos del cliente)

	def openTicket(self, tipo_comprobante = "T"):
		"""Abre documento fiscal"""
		jdata = OrderedDict()
		jdata['cmd'] = self.CMD_OPEN_FISCAL_RECEIPT
		jdata['field'] = ["", tipo_comprobante]

		return self._sendCommand( jdata )

	def openBillTicket(self, tipo_comprobante, name, address, doc, docType, ivaType):
		"""
		Abre un ticket-factura
			@param  type        Tipo de Factura T = TiqueFactura / N = TiqueNotaCredito
			@param  name        Nombre del cliente
			@param  address     Domicilio
			@param  doc         Documento del cliente según docType
			@param  docType     Tipo de documento
			@param  ivaType     Tipo de IVA
		"""
		if tipo_comprobante != "N":
			#si no es nota de crédito, el tipo es T, la letra del tipo factura se determina automaticamente
			tipo_comprobante = 'T'

		if ivaType == 'I':
			self.esFacturaA = True
		jdata = OrderedDict()
		jdata['cmd'] = self.CMD_OPEN_BILL_TICKET
		jdata['field'] = [
						tipo_comprobante, #T para Tique-Factura o N para Tique-Nota de crédito (la letra de Factura se determina según la responsabilidad del cliente)
						"",
						"",
						0,
						"",
						0,
						'I', #responsabilidad en modo entrenamiento (ignorado cuando la impresora es inicializada)
						ivaType or 'F', #responsabilidad del cliente (si no hay, mandamos consumidor final)
						name, #nombre del cliente
						"", #2da linea nombre del cliente
						docType, #tipo doc del cliente
						str(doc), #nro doc del cliente
						"",
						address, #direccion del cliente
						"",
						"",
						"",
						"",
						"",
					]

		return self._sendCommand(jdata)
		

	def openBillCreditTicket(self, type, name, address, doc, docType, ivaType, reference="NC"):

		return self.openBillTicket( "N", name, address, doc, docType, ivaType )

	def addAdditional(self, description, amount, iva, negative=False):
		"""Agrega un descuento o recargo general a la Factura o Ticket.
			@param description  Descripción
			@param amount       Importe (sin iva en FC A, sino con IVA)
			@param iva          Porcentaje de Iva
			@param negative     Si negative = True, se añadira el monto como descuento, sino, sera un recargo
		"""

		jdata = OrderedDict()
		jdata['cmd'] = self.CMD_ADD_PAYMENT

		if self.esFacturaA == True:
			#descontamos el IVA al descuento / recargo
			amount = round((amount / ((100 + float(iva)) / 100)), 2)

		tipo_op = 'D'
		desc_default = 'Descuento'
		if negative == False:
			tipo_op = 'R'
			desc_default = 'Recargo'

		jdata['field'] = [description or desc_default, amount, tipo_op, ""] #el ultimo campo es codigo matrix, lo enviamos vacio


		return self._sendCommand(jdata)
		

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
		"""Cierre Z (diario) o X (parcial)
			@param type     Z (diario), X (parcial)
		"""
		jdata = OrderedDict()
		jdata['cmd'] = self.CMD_DAILY_CLOSE
		jdata['field'] = [type.upper(),"P"]

		return self._sendCommand( jdata )

	def getWarnings(self):
		return []

	def openDrawer(self):
		"""Abrir cajón del dinero"""
		jdata = OrderedDict()
		jdata['cmd'] = self. CMD_OPEN_DRAWER
		jdata['field'] = []

		return self._sendCommand( jdata )
