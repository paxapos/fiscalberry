# coding=utf-8

import json
import ConfigParser

CONFIG_FILE_NAME = "config.ini"
CONFIG_IMPRESORA_FISCAL_SECTION_NAME = "IMPRESORA_FISCAL"

class TraductorException(Exception):
	pass

class Traductor:
	"""Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""

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
				 marca=None, 
				 deviceFile=None, 
				 modelo=None, 
				 driverName=None
				 ):

		config = ConfigParser.RawConfigParser()
		config.read(CONFIG_FILE_NAME)
		if not marca:	
			marca = config.get('IMPRESORA_FISCAL', "marca")
		if not modelo:	
			modelo = config.get('IMPRESORA_FISCAL', "modelo")
		if not deviceFile:	
			deviceFile = config.get('IMPRESORA_FISCAL', "path")
		if not driverName:	
			driverName = config.get('IMPRESORA_FISCAL', "driver")
		if marca == "Epson":
			from Comandos.EpsonComandos import EpsonComandos
			self.comando = EpsonComandos(deviceFile, driverName=driverName)
		elif marca == "Hasar":
			from Comandos.HasarComandos import HasarComandos
			self.comando = HasarComandos(deviceFile, driverName=driverName)
		else:
			raise TraductorException("Debe seleccionar un juego de comandos valido de la Carpeta /Comandos")

		self.printer = self.comando
		


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
		return self.printer.dailyClose(type)


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


	def _getStatus(self):
		config = ConfigParser.RawConfigParser()

		config.read(CONFIG_FILE_NAME)
		marca  = config.get(CONFIG_IMPRESORA_FISCAL_SECTION_NAME, "marca")
		modelo = config.get(CONFIG_IMPRESORA_FISCAL_SECTION_NAME, "modelo")
		path   = config.get(CONFIG_IMPRESORA_FISCAL_SECTION_NAME, "path")
		driver = config.get(CONFIG_IMPRESORA_FISCAL_SECTION_NAME, "driver")

		return {
			"marca": marca,
			"modelo": modelo,
			"path": path,
			"driver": driver
		}

	def _openDrawer(self):
		"Abrir caja registradora"
		return self.printer.openDrawer()


	def _consultarUltNro(self, tipo_cbte):
		"Devuelve el último número de comprobante"
		
		letra_cbte = tipo_cbte[-1] if len(tipo_cbte) > 1 else None
		return self.printer.getLastNumber(letra_cbte)


	def is_json(self, myjson):
	    try:
	        json_object = json.loads(myjson)
	    except ValueError, e:
	        return False
	    return True

	def json_to_comando( self, jsonTicket ):
		# leer y procesar una factura en formato JSON
		print("Iniciando procesamiento de json...")
		

		print "esto es lo que estoy viendo"
		print jsonTicket

		if 'printTicket' in jsonTicket:
			ok = self._abrirComprobante(**jsonTicket['printTicket']["encabezado"])

			if "items" in jsonTicket['printTicket']:
				for item in jsonTicket['printTicket']["items"]:
					ok = self._imprimirItem(**item)
			else:
				raise TraductorException("Debe incluir 'items' en el JSON")

			if "pagos" in jsonTicket['printTicket']:
				for pago in jsonTicket['printTicket']["pagos"]:
					ok = self._imprimirPago(**pago)
			return self._cerrarComprobante()

		if 'dailyClose' in jsonTicket:
			return self._dailyClose(**jsonTicket["dailyClose"])

		if 'openDrawer' in jsonTicket:
			return self._openDrawer()


		if 'configure' in jsonTicket:
			return self._configure(**jsonTicket["configure"])

		if 'getStatus' in jsonTicket:
			return self._getStatus()
			
