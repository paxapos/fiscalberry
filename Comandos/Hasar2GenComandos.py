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
		"RESPONSABLE_NO_INSCRIPTO": 'N',
		"EXENTO": 'ResponsableExento',
		"NO_RESPONSABLE": 'NoResponsable',
		"CONSUMIDOR_FINAL": 'ConsumidorFinal',
		"RESPONSABLE_NO_INSCRIPTO_BIENES_DE_USO": 'B',
		"RESPONSABLE_MONOTRIBUTO": 'Monotributo',
		"MONOTRIBUTISTA_SOCIAL": 'MonotributoSocial',
		"PEQUENIO_CONTRIBUYENTE_EVENTUAL": 'Eventual',
		"PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL": 'EventualSocial',
		"NO_CATEGORIZADO": 'NoCategorizado',
	}

	comprobanteTypes = {
		"T": 'Tique',
		"FB": 'TiqueFacturaB',
		"FA": 'TiqueFacturaA',
		"FC": 'TiqueFacturaC',
		"NCT": 'TiqueNotaCredito',
		"NCA": 'TiqueNotaCreditoA',
		"NCB": 'TiqueNotaCreditoB',
		"NCC": 'TiqueNotaCreditoC',
		"NDA": 'TiqueNotaDebitoA',
		"NDB": 'TiqueNotaDebitoB',
		"NDC": 'TiqueNotaDebitoC',
	}


	def getStatus(self, *args):
		jdata = {"ConsultarEstado":{"CodigoComprobante" : "81"}}

		self.conector.sendCommand( jdata )

	def setTrailer(self, trailer=None):
		"""Establecer pie"""
		pass

	def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
		pass


	def _setCustomerData(self, name=" ", address=" ", doc=" ", docType=" ", ivaType="T"):

		docTypeCode = self.docTypes.get(docType)
		ivaTypesCode = self.ivaTypes.get(ivaType)
		jdata = {
			"CargarDatosCliente":{
				"RazonSocial" : name,
				"NumeroDocumento" : doc,
				"ResponsabilidadIVA" : "ResponsableInscripto",
				"TipoDocumento" : docTypeCode,
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
			"Texto" : text,
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

	
	def __openTicket(self, tipoComprobante):
		ctype = self.comprobanteTypes.get( tipoComprobante )
		jdata = {"AbrirDocumento":{
			"CodigoComprobante" : ctype
			}
		}
	
		return self.conector.sendCommand( jdata )


	# Ticket fiscal (siempre es a consumidor final, no permite datos del cliente)

	def openTicket(self, comprobanteType = "T"):
		"""Abre documento fiscal"""
		self.__openTicket( comprobanteType )

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
			self._setCustomerData(name, address, doc, docType, ivaType)

		return self.__openTicket( "F"+type )
		

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
		if name and doc:
			self._setCustomerData(name, address, doc, docType, ivaType)

		self.__cargarNumReferencia(reference)
		return self.__openTicket( "NC"+type )

	def __cargarNumReferencia(self, numero):

		jdata = {"ConsultarDatosInicializacion" : {}}
		retdata = self.conector.sendCommand( jdata )

		numpos = 1
		if retdata.has_key("ConsultarDatosInicializacion") and retdata["ConsultarDatosInicializacion"].has_key("NumeroPos"):
			# agarro el numero de punto de venta directo desde la fiscal
			numpos = retdata["ConsultarDatosInicializacion"]["NumeroPos"]

		jdata = {"CargarDocumentoAsociado":{
			"NumeroLinea" : "1",
			"CodigoComprobante" : "RemitoR",
			"NumeroPos" : numpos,
			"NumeroComprobante" : numero
		}}

		return self.conector.sendCommand( jdata )

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
		if name and doc:
			self._setCustomerData(name, address, doc, docType, ivaType)

		return self.__openTicket( "ND"+type )

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
