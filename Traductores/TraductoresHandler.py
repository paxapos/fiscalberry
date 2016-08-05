# coding=utf-8

import json
import ConfigParser
import logging
import importlib

CONFIG_FILE_NAME = "config.ini"
CONFIG_IMPRESORA_FISCAL_SECTION_NAME = "IMPRESORA_FISCAL"

class TraductorException(Exception):
	pass

class TraductoresHandler:
	"""Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""



	# es un diccionario como clave va el nombre de la impresora que funciona como cola
	# cada KEY es una printerName y contiene un a instancia de TraductorReceipt o TraductorFiscal dependiendo
	# si la impresora es fiscal o receipt
	traductores = {}



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

	def __init__(self):
		self.__create_config_if_not_exists()
		self.__init_cola_traductores_printer()
		

	def __init_cola_traductores_printer(self):

		config = ConfigParser.ConfigParser()
		config.read(CONFIG_FILE_NAME)

		secs = config.sections()

		dictConf = {s:dict(config.items(s)) for s in config.sections()}
		# para cada impresora le voy a crear su juego de comandos con sui respectivo traductor
		for s in secs:
			# si la seccion es "SERVIDOR", no hacer caso y continuar con el resto
			if s == "SERVIDOR":
				continue
			print s
			dictSectionConf = dictConf[s]
			marca = dictSectionConf.get("marca")
			del dictSectionConf['marca']
			# instanciar los comandos dinamicamente
			libraryName = "Comandos."+marca+"Comandos"
			comandoModule = importlib.import_module(libraryName)
			comandoClass = getattr(comandoModule, marca+"Comandos")
			comando = comandoClass(**dictSectionConf)
			traductorComando = comando.traductor
		
			# inicializo la cola por cada seccion o sea cada impresora
			self.traductores.setdefault(s, traductorComando) 


		
	def __create_config_if_not_exists(self):
		import os.path
		if not os.path.isfile(CONFIG_FILE_NAME):
			import shutil
			shutil.copy ("config.ini.install", CONFIG_FILE_NAME)



	def debugLog(self):
		"Devolver bitácora de depuración"
		msg = self.log.getvalue()
		return msg    

	


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

	

	def _getStatus(self, printerName):
		config = ConfigParser.RawConfigParser()

		config.read(CONFIG_FILE_NAME)
		marca  = config.get(printerName, "marca")
		modelo = None
		if config.has_option(printerName, "modelo"):
			modelo = config.get(printerName, "modelo")
		path   = config.get(printerName, "path")
		driver = config.get(printerName, "driver")

		return {
			"marca": marca,
			"modelo": modelo,
			"path": path,
			"driver": driver
		}



	def is_json(self, myjson):
	    try:
	        json_object = json.loads(myjson)
	    except ValueError, e:
	        return False
	    return True





	def json_to_comando( self, jsonTicket ):
		# leer y procesar una factura en formato JSON
		logging.info("Iniciando procesamiento de json...")
		print jsonTicket

		rta = {"rta":""}

		# dejar la impresora por defecto inicializada en una variable auxiliar
		printerDefault = self.printer

		# seleccionar impresora
		# esto se debe ejecutar antes que cualquier otro comando
		if 'printerName' in jsonTicket:
			traductor = self.traductores.get( jsonTicket['printerName'] )
			traductor.encolar( jsonTicket )
		else:
			# aciones de comando genericos de Ststus y control
			if 'getStatus' in jsonTicket:
				rta["rta"] =  self._getStatus()

			if 'getAvaliablePrinters' in jsonTicket:
				rta["rta"] =  self._getAvaliablePrinters()

			if 'configure' in jsonTicket:
				rta["rta"] =  self._configure(**jsonTicket["configure"])

			

		self.encolar( self.currentPrinterName, jsonTicket )

		
