# -*- coding: iso-8859-1 -*-
import string
import types
import logging
import unicodedata
from Comandos.ComandoFiscalInterface import ComandoFiscalInterface
from Drivers.FiscalPrinterDriver import PrinterException
from ComandoInterface import formatText



class Hasar2GenComandos(ComandoFiscalInterface):
	# el traductor puede ser: TraductorFiscal o TraductorReceipt
	# path al modulo de traductor que este comando necesita
	traductorModule = "Traductores.TraductorFiscal"

	DEFAULT_DRIVER = "Json"

	
	AVAILABLE_MODELS = ["PT-1000F","PT-250F", "P-HAS-5100-FAR"]


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
		"CUIT": 'C',
		"LIBRETA_ENROLAMIENTO": '0',
		"LIBRETA_CIVICA": '1',
		"DNI": '2',
		"PASAPORTE": '3',
		"CEDULA": '4',
		"SIN_CALIFICADOR": ' ',
	}

	ivaTypes = {
		"RESPONSABLE_INSCRIPTO": 'I',
		"RESPONSABLE_NO_INSCRIPTO": 'N',
		"EXENTO": 'E',
		"NO_RESPONSABLE": 'A',
		"CONSUMIDOR_FINAL": 'C',
		"RESPONSABLE_NO_INSCRIPTO_BIENES_DE_USO": 'B',
		"RESPONSABLE_MONOTRIBUTO": 'M',
		"MONOTRIBUTISTA_SOCIAL": 'S',
		"PEQUENIO_CONTRIBUYENTE_EVENTUAL": 'V',
		"PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL": 'W',
		"NO_CATEGORIZADO": 'T',
	}



	def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
		pass


	def _setCustomerData(self, name=" ", address=" ", doc=" ", docType=" ", ivaType="T"):

		jdata = {
			"CargarDatosCliente":
			{
			"RazonSocial" : name,
			"NumeroDocumento" : doc,
			"ResponsabilidadIVA" : "ResponsableInscripto",
			"TipoDocumento" : "TipoCUIT",
			"Domicilio" : address
			}
			}

		self.conector.sendCommand( jdata )

	# Documentos no fiscales

	def openNonFiscalReceipt(self):
		"""Abre documento no fiscal"""
		pass

	def printFiscalText(self, text):
		jdata = {"ImprimirTextoFiscal":{
			"Atributos" : [ "Centrado" ],
			"Texto" : "Producto en oferta: Sólo por hoy !",
			"ModoDisplay" : "DisplayNo"
		}}

		self.conector.sendCommand( jdata )

	def printNonFiscalText(self, text):
		"""Imprime texto fiscal. Si supera el límite de la linea se trunca."""
		pass
		{"ImprimirTextoGenerico":{
			"Atributos" : [ "Negrita" ],
			"Texto" : text,
			"ModoDisplay" : "DisplayNo"
		}}

		self.conector.sendCommand( jdata )

	def closeDocument(self, copias = 0, email = None):
		"""Cierra el documento que esté abierto"""
		jdata = {"CerrarDocumento": {
			"Copias" : str(copias),		
		}}

		jdata["CerrarDocumento"]["DireccionEMail"] = email

		self.conector.sendCommand( jdata )


	def cancelDocument(self):
		"""Cancela el documento que esté abierto"""
		jdata = {"Cancelar" : {}}
		self.conector.sendCommand( jdata )

	def addItem(self, description, quantity, price, iva, discount, discountDescription, negative=False, *kargs):
		"""Agrega un item a la FC.
			@param description          Descripción del item. Puede ser un string o una lista.
				Si es una lista cada valor va en una línea.
			@param quantity             Cantidad
			@param price                Precio (incluye el iva si la FC es B o C, si es A no lo incluye)
			@param iva                  Porcentaje de iva
			@param negative             True->Resta de la FC
			@param discount             Importe de descuento
			@param discountDescription  Descripción del descuento
		"""
		jdata = {"ImprimirItem": {
					"Descripcion" : description,
					"Cantidad" : quantity,
					"PrecioUnitario" : price,
					"CondicionIVA" : "Gravado",
					"AlicuotaIVA" : iva,
					"OperacionMonto" : "ModoSumaMonto",
					"TipoImpuestoInterno" : "IIVariableKIVA",
					"MagnitudImpuestoInterno" : "0.00",
					"ModoDisplay" : "DisplayNo",
					"ModoBaseTotal" : "ModoPrecioTotal",
					}
				}
		self.conector.sendCommand( jdata )

		if discount and not negative:
			jdata= {"ImprimirDescuentoItem": {
				"Descripcion" : discountDescription,
				"Monto" : discount,
				"ModoDisplay" : "DisplayNo",
				"ModoBaseTotal" : "ModoPrecioTotal"
				}}
			self.conector.sendCommand( jdata )

		if discount and negative:
			jdata = {"ImprimirAjuste":{
				"Descripcion" : discountDescription,
				"Monto" : discount,
				"ModoDisplay" : "DisplayNo",
				"Operacion" : "AjusteNeg"
			}}

			self.conector.sendCommand( jdata )

	def addPayment(self, description, payment):
		"""Agrega un pago a la FC.
			@param description  Descripción
			@param payment      Importe
		"""
		jdata = {"ImprimirPago":	{
		"Descripcion" : description,
		"Monto" : payment,
		"Operacion" : "Pagar",
		"ModoDisplay" : "DisplayNo",
		}}

		self.conector.sendCommand( jdata )

	

	# Ticket fiscal (siempre es a consumidor final, no permite datos del cliente)

	def openTicket(self):
		"""Abre documento fiscal"""
		jdata = {"AbrirDocumento":{
			"CodigoComprobante" : "TiqueFacturaB"
			}
		}
	
		self.conector.sendCommand( jdata )

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
		if name and doc:
			_setCustomerData(name, address, doc, docType, ivaType)

		jdata = {"AbrirDocumento":{
			"CodigoComprobante" : "TiqueFacturaB"
			}
		}
	
		self.conector.sendCommand( jdata )

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

	def addAdditional(self, description, amount, iva, negative=False):
		"""Agrega un adicional a la FC.
			@param description  Descripción
			@param amount       Importe (sin iva en FC A, sino con IVA)
			@param iva          Porcentaje de Iva
			@param negative True->Descuento, False->Recargo"""
		pass

		

	def setCodigoBarras(self, numero , tipoCodigo = "CodigoTipoI2OF5", imprimeNumero =  "ImprimeNumerosCodigo" ):
		jdata = {"CargarCodigoBarras":
			{
			"TipoCodigo" : tipoCodigo,
			"Numero" : numero,
			"ImprimeNumero" : imprimeNumero,
			"Almacena" : "ProgramaCodigo"
			}
		}

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
		"""Cancela cualquier documento abierto, sea del tipo que sea.
		   No requiere que previamente se haya abierto el documento por este objeto.
		   Se usa para destrabar la impresora."""
		pass

	def dailyClose(self, type):
		"""Cierre Z (diario) o X (parcial)
			@param type     Z (diario), X (parcial)
		"""
		if type.upper() == "Z":
			reporteTal = "ReporteZ"
		else:
			reporteTal = "ReporteX"
		jdata = {"CerrarJornadaFiscal":{
			"Reporte" : reporteTal
		}}

		self.conector.sendCommand( jdata )

	def getWarnings(self):
		return []

	def openDrawer(self):
		"""Abrir cajón del dinero - No es mandatory implementarlo"""
		jdata = {"AbrirCajonDinero" : {}}

		self.conector.sendCommand( jdata )
