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
		

	def getWarnings(self):
		""" Recolecta los warning que puedan ir arrojando las impresoraas
			devuelve un listado de warnings
		"""
		collect_warnings = {}
		for trad in self.traductores:
			if self.traductores[trad]:
				warn = self.traductores[trad].comando.getWarnings()
				if warn:
					collect_warnings[trad] = warn
		return collect_warnings


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
			savedPath = os.getcwd()
			newpath = os.path.dirname(os.path.realpath(__file__))
			os.chdir(newpath)
			os.chdir("../")
			import shutil
			shutil.copy ("config.ini.install", CONFIG_FILE_NAME)
			os.chdir(savedPath)



	def debugLog(self):
		"Devolver bitácora de depuración"
		msg = self.log.getvalue()
		return msg    

	


	def _configure(self, printerName, **kwargs):
		"Configura generando o modificando el archivo configure.ini"

		config = ConfigParser.RawConfigParser()
		config.read(CONFIG_FILE_NAME)

		if not config.has_section(printerName):
			config.add_section(printerName)

		for param in kwargs:
			config.set(printerName, param, kwargs[param])

		with open(CONFIG_FILE_NAME, 'w') as configfile:
			config.write(configfile)

		return {
			"action": "configure",
			"rta": "ok"
		}

	def _getAvaliablePrinters(self):
		config = ConfigParser.RawConfigParser()
		config.read(CONFIG_FILE_NAME)
		# la primer seccion corresponde a SERVER, el resto son las impresoras
		rta = {
			"action": "getAvaliablePrinters",
			"rta": config.sections()[1:]
		}

		return rta

	

	def _getStatus(self, *args):
		resdict = {"action": "getStatus", "rta":{}}
		for tradu in self.traductores:
			if self.traductores[tradu]:
				resdict["rta"][tradu] = "ONLINE"
			else:
				resdict["rta"][tradu] = "OFFLINE"
		return resdict


	def is_json(self, myjson):
		try:
			json_object = json.loads(myjson)
		except ValueError, e:
			return False
		return True




	def json_to_comando	( self, jsonTicket ):
		""" leer y procesar una factura en formato JSON
		"""
		logging.info("Iniciando procesamiento de json...")

		print jsonTicket

		
		rta = {"rta":""}
		# seleccionar impresora
		# esto se debe ejecutar antes que cualquier otro comando
		if 'printerName' in jsonTicket:
			printerName = jsonTicket.pop('printerName')
			traductor = self.traductores.get( printerName )
			if traductor:
				if traductor.comando.conector is not None:
					rta["rta"] = traductor.run( jsonTicket )
				else:
					logging.info("el Driver no esta inicializado para la impresora %s"%printerName)
			else:
				raise TraductorException("En el archivo de configuracion no existe la impresora: '%s'"%printerName)
		
		# aciones de comando genericos de Ststus y control
		elif 'getStatus' in jsonTicket:
			rta["rta"] =  self._getStatus()

		elif 'getAvaliablePrinters' in jsonTicket:
			rta["rta"] =  self._getAvaliablePrinters()

		elif 'configure' in jsonTicket:
			rta["rta"] =  self._configure(**jsonTicket["configure"])

		else:
			rta["err"] = "No se paso un comandio de accion generico ni el nombre de la impresora printerName"

		return rta
