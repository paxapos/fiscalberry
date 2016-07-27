# coding=utf-8

import json
import ConfigParser

CONFIG_FILE_NAME = "config.ini"
CONFIG_IMPRESORA_FISCAL_SECTION_NAME = "IMPRESORA_FISCAL"

class TraductorException(Exception):
	pass

class Traductor:
	"""Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""
	currentPrinterName = CONFIG_IMPRESORA_FISCAL_SECTION_NAME
	defaultPrinterName = CONFIG_IMPRESORA_FISCAL_SECTION_NAME

	# RG1785/04
	cbte_fiscal_map = {
							1: 'FA', 
							2: 'NDA', 
							3: 'NCA', 
							6: 'FB', 
							7: 'NDB', 
							8: 'NCB', 
							11: 'FC', 
							12: 'NDC', 
							13: 'NDC',
							81:	'FA', #tique factura A
							82: 'FB', #tique factura B
							83: 'T',  # tiques
						}

	pos_fiscal_map = {
							1:  "IVA_TYPE_RESPONSABLE_INSCRIPTO",
							2:	"IVA_TYPE_RESPONSABLE_NO_INSCRIPTO",
							3:	"IVA_TYPE_NO_RESPONSABLE",
							4:	"IVA_TYPE_EXENTO",
							5:	"IVA_TYPE_CONSUMIDOR_FINAL",
							6:	"IVA_TYPE_RESPONSABLE_MONOTRIBUTO",
							7:	"IVA_TYPE_NO_CATEGORIZADO",
							12:	"IVA_TYPE_PEQUENIO_CONTRIBUYENTE_EVENTUAL",
							13: "IVA_TYPE_MONOTRIBUTISTA_SOCIAL",
							14:	"IVA_TYPE_PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL",
						}
	doc_fiscal_map = {
							96: "DOC_TYPE_DNI",
							80: "DOC_TYPE_CUIT",
							89: "DOC_TYPE_LIBRETA_ENROLAMIENTO",
							90: "DOC_TYPE_LIBRETA_CIVICA",
							00: "DOC_TYPE_CEDULA",
							94: "DOC_TYPE_PASAPORTE", 
							99: "DOC_TYPE_SIN_CALIFICADOR",
					  	}

	def __init__(self,
				 printerName,
				 marca=None, 
				 deviceFile=None, 
				 modelo=None, 
				 driverName=None
				 ):
		self.printer = self._select_printer(printerName, marca, deviceFile, modelo, driverName)
		

	def _select_printer(self,
						 printerName,
						 marca=None, 
						 deviceFile=None, 
						 modelo=None, 
						 driverName=None
						 ):
		self.currentPrinterName = printerName
		comando = None
		import os.path
		if not os.path.isfile(CONFIG_FILE_NAME):
			import shutil
			shutil.copy ("config.ini.install", CONFIG_FILE_NAME)

		config = ConfigParser.RawConfigParser()
		config.read(CONFIG_FILE_NAME)
		if not marca:	
			marca = config.get(printerName, "marca")
		if not modelo:
			modelo = None
			if config.has_option(printerName, "modelo"):
				modelo = config.get(printerName, "modelo")
		if not deviceFile:	
			deviceFile = config.get(printerName, "path")
		if not driverName:	
			driverName = config.get(printerName, "driver")

		if marca == "Epson":
			from Comandos.EpsonComandos import EpsonComandos
			comando = EpsonComandos(deviceFile, driverName=driverName)
		elif marca == "Hasar":
			from Comandos.HasarComandos import HasarComandos
			comando = HasarComandos(deviceFile, driverName=driverName)
		elif marca == "Bematech":
			from Comandos.BematechComandos import BematechComandos
			comando = BematechComandos(deviceFile, driverName=driverName)
		elif marca == "EscP":
			from Comandos.EscPComandos import EscPComandos
			comando = EscPComandos(deviceFile, driverName=driverName)
		else:
			raise TraductorException("Debe seleccionar un juego de comandos valido de la Carpeta /Comandos")

		return comando

	def debugLog(self):
		"Devolver bitácora de depuración"
		msg = self.log.getvalue()
		return msg    

	def _abrirComprobante(self, 
						 tipo_cbte="T", 							# tique
						 tipo_responsable="CONSUMIDOR_FINAL",
						 tipo_doc="SIN_CALIFICADOR", nro_doc=0,     # sin especificar
						 nombre_cliente="", domicilio_cliente="",
						 referencia=None,                           # comprobante original (ND/NC)
						 **kwargs
						 ):
		"Creo un objeto factura (internamente) e imprime el encabezado"
		# crear la estructura interna
		self.factura = {"encabezado": dict(tipo_cbte=tipo_cbte,
										   tipo_responsable=tipo_responsable,
										   tipo_doc=tipo_doc, nro_doc=nro_doc,
										   nombre_cliente=nombre_cliente, 
										   domicilio_cliente=domicilio_cliente,
										   referencia=referencia),
						"items": [], "pagos": []}
		printer = self.printer


		letra_cbte = tipo_cbte[-1] if len(tipo_cbte) > 1 else None
		
		# mapear el tipo de cliente (posicion/categoria)
		pos_fiscal = printer.ivaTypes.get(tipo_responsable)
		
		# mapear el numero de documento según RG1361
		doc_fiscal = printer.docTypes.get(tipo_doc)

		# cancelar y volver a un estado conocido
		printer.cancelAnyDocument()
		ret = False
		# enviar los comandos de apertura de comprobante fiscal:
		if tipo_cbte.startswith('T'):
			if letra_cbte:
				ret = printer.openTicket(letra_cbte)
			else:
				ret = printer.openTicket()
		elif tipo_cbte.startswith("F"):
			ret = printer.openBillTicket(letra_cbte, nombre_cliente, domicilio_cliente, 
										 nro_doc, doc_fiscal, pos_fiscal)
		elif tipo_cbte.startswith("ND"):
			ret = printer.openDebitNoteTicket(letra_cbte, nombre_cliente, 
											  domicilio_cliente, nro_doc, doc_fiscal, 
											  pos_fiscal)
		elif tipo_cbte.startswith("NC"):
			ret = printer.openBillCreditTicket(letra_cbte, nombre_cliente, 
											   domicilio_cliente, nro_doc, doc_fiscal, 
											   pos_fiscal, referencia)
		
		return ret

	def _imprimirItem(self, ds, qty, importe, alic_iva=21.):
		"Envia un item (descripcion, cantidad, etc.) a una factura"
		self.factura["items"].append(dict(ds=ds, qty=qty, 
										  importe=importe, alic_iva=alic_iva))
		##ds = unicode(ds, "latin1") # convierto a latin1
		# Nota: no se calcula neto, iva, etc (deben venir calculados!)
		discount = discountDescription =  None
		return self.printer.addItem(ds, float(qty), float(importe), float(alic_iva), 
									discount, discountDescription)

	def _imprimirPago(self, ds, importe):
		"Imprime una linea con la forma de pago y monto"
		self.factura["pagos"].append(dict(ds=ds, importe=importe))
		return self.printer.addPayment(ds, float(importe))

	def _cerrarComprobante(self):
		"Envia el comando para cerrar un comprobante Fiscal"
		return self.printer.closeDocument()


	def _dailyClose(self, type):
		"Comando X o Z"
		ret = self.printer.dailyClose(type)
		return ret


	def _configure(self, printerName,  marca, modelo, path, driver=None):
		"Configura generando o modificando el archivo configure.ini"

		config = ConfigParser.RawConfigParser()
		config.read(CONFIG_FILE_NAME)

		if not config.has_section(printerName):
			config.add_section(printerName)
		config.set(printerName, 'marca', marca)
		config.set(printerName, 'modelo', modelo)
		config.set(printerName, 'path', path)
		config.set(printerName, 'driver', driver)

		with open(CONFIG_FILE_NAME, 'w') as configfile:
			config.write(configfile)

	def _getAvaliablePrinters(self):
		config = ConfigParser.RawConfigParser()
		config.read(CONFIG_FILE_NAME)
		# la primer seccion corresponde a SERVER, el resto son las impresoras
		return config.sections()[1:]

	def _setHeader(self, header):
		"SetHeader"
		ret = self.printer.setHeader(header)
		return ret

	def _setTrailer(self, trailer):
		"SetTrailer"
		ret = self.printer.setTrailer(trailer)
		return ret

	def _getStatus(self):
		config = ConfigParser.RawConfigParser()

		config.read(CONFIG_FILE_NAME)
		marca  = config.get(self.currentPrinterName, "marca")
		modelo = None
		if config.has_option(self.currentPrinterName, "modelo"):
			modelo = config.get(self.currentPrinterName, "modelo")
		path   = config.get(self.currentPrinterName, "path")
		driver = config.get(self.currentPrinterName, "driver")

		return {
			"marca": marca,
			"modelo": modelo,
			"path": path,
			"driver": driver
		}

	def _openDrawer(self):
		"Abrir caja registradora"
		return self.printer.openDrawer()


	def _getLastNumber(self, tipo_cbte):
		"Devuelve el último número de comprobante"
		
		letra_cbte = tipo_cbte[-1] if len(tipo_cbte) > 1 else None
		return self.printer.getLastNumber(letra_cbte)

	def _cancelDocument(self):
		"Cancelar comprobante en curso"
		return self.printer.cancelDocument()

	def _printRemito(self):
		"Imprime un Remito, comando de accion valido solo para Comandos de Receipt"
		return self.printer.printRemito()

	def _printComanda(self, comanda, mesa, mozo):
		"Imprime una Comanda, comando de accion valido solo para Comandos de Receipt"
		return self.printer.printComanda(comanda, mesa, mozo)


	def is_json(self, myjson):
	    try:
	        json_object = json.loads(myjson)
	    except ValueError, e:
	        return False
	    return True

	def json_to_comando( self, jsonTicket ):
		# leer y procesar una factura en formato JSON
		print("Iniciando procesamiento de json...")
		

		rta = {"rta":""}

		# dejar la impresora por defecto inicializada en una variable auxiliar
		printerDefault = self.printer
		
		# seleccionar impresora
		# esto se debe ejecutar antes que cualquier otro comando
		if 'printerName' in jsonTicket:
			print("cambiando de impresora a %s"%jsonTicket['printerName'])
			self.printer = self._select_printer(jsonTicket['printerName'])

		if 'printRemito' in jsonTicket:
			rta["rta"] =  self._printRemito(**jsonTicket["printRemito"])

		if 'printComanda' in jsonTicket:
			rta["rta"] =  self._printComanda(**jsonTicket["printComanda"])

		if 'cancelDocument' in jsonTicket:
			rta["rta"] =  self._cancelDocument()

		if 'dailyClose' in jsonTicket:
			rta["rta"] =  self._dailyClose(jsonTicket["dailyClose"])

		if 'openDrawer' in jsonTicket:
			rta["rta"] =  self._openDrawer()


		if 'configure' in jsonTicket:
			rta["rta"] =  self._configure(**jsonTicket["configure"])

		if 'getLastNumber' in jsonTicket:
			rta["rta"] =  self._getLastNumber(jsonTicket["getLastNumber"])			

		if 'getStatus' in jsonTicket:
			rta["rta"] =  self._getStatus()

		if 'getAvaliablePrinters' in jsonTicket:
			rta["rta"] =  self._getAvaliablePrinters()
		
		if 'setHeader' in jsonTicket:
			rta["rta"] =  self._setHeader( jsonTicket["setHeader"] )

		if 'setTrailer' in jsonTicket:
			rta["rta"] =  self._setTrailer( jsonTicket["setTrailer"] )

		if 'printTicket' in jsonTicket:
			ok = self._abrirComprobante(**jsonTicket['printTicket']["encabezado"])

			if "items" in jsonTicket['printTicket']:
				for item in jsonTicket['printTicket']["items"]:
					ok = self._imprimirItem(**item)
			else:
				raise TraductorException("Debe incluir 'items' en el JSON")

			if "pagos" in jsonTicket['printTicket']:
				for pago in jsonTicket['printTicket']["pagos"]:
					print pago
					ok = self._imprimirPago(**pago)
			rta["rta"] =  self._cerrarComprobante()

		# vuelvo a poner la impresora que estaba por default inicializada
		self.printer = printerDefault
		self.currentPrinterName = self.defaultPrinterName
		return rta
