# coding=utf-8

import json
import ConfigParser
import logging
import importlib
import socket
import threading

def set_interval(func, sec):
    def func_wrapper():
        set_interval(func, sec)
        func()
    t = threading.Timer(sec, func_wrapper)
    t.start()
    return t


CONFIG_FILE_NAME = "config.ini"

# es un diccionario como clave va el nombre de la impresora que funciona como cola
# cada KEY es una printerName y contiene un a instancia de TraductorReceipt o TraductorFiscal dependiendo
# si la impresora es fiscal o receipt
traductores = {}

class TraductorException(Exception):
	pass

class TraductoresHandler:
	"""Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""



	# traductores = {}

	config = None

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
							13: 'NCC',
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
		config = ConfigParser.ConfigParser()
		config.read(CONFIG_FILE_NAME)

		self.config = config

		self.__create_config_if_not_exists()
		self.__init_cola_traductores_printer()
		#self.__init_keep_looking_for_device_connected()

		
	def get_traductores():
		global traductores
		return traductores

	def __init_keep_looking_for_device_connected(self):
		def recorrer_traductores_y_comprobar():
			global traductores
			logging.info("Iniciando procesamiento de json...")
			for t in traductores:
				print "estoy por verificando conexion de %s"%t
				if not traductores[t].comando.conector:
					print "*** NO conectada"
					logging.info("la impresora %s esta desconectada y voy a reintentar conectarla"%t)
					self.init_printer_traductor(t)
				else:
					print "ya estaba conectado"

		set_interval(recorrer_traductores_y_comprobar, 10)



	def getWarnings(self):
		""" Recolecta los warning que puedan ir arrojando las impresoraas
			devuelve un listado de warnings
		"""
		global traductores
		collect_warnings = {}
		for trad in traductores:
			if traductores[trad]:
				warn = traductores[trad].comando.getWarnings()
				if warn:
					collect_warnings[trad] = warn
		return collect_warnings


	def get_config_for_printer(self, printerName):
		dictConf = {s:dict(self.config.items(s)) for s in self.config.sections()}

		return dictConf[printerName]


	def get_sections_from_config_file( self):
		config = ConfigParser.ConfigParser()
		config.read(CONFIG_FILE_NAME)

		return  config.sections()

	def init_printer_traductor(self, printerName):
		global traductores
		dictSectionConf = self.get_config_for_printer(printerName)
		marca = dictSectionConf.get("marca")
		del dictSectionConf['marca']
		# instanciar los comandos dinamicamente
		libraryName = "Comandos."+marca+"Comandos"
		comandoModule = importlib.import_module(libraryName)
		comandoClass = getattr(comandoModule, marca+"Comandos")
		
		comando = comandoClass(**dictSectionConf)
		traductorComando = comando.traductor

		# inicializo la cola por cada seccion o sea cada impresora
		traductores.setdefault(printerName, traductorComando) 



	def __init_cola_traductores_printer(self):

		secs = self.get_sections_from_config_file()

		# para cada impresora le voy a crear su juego de comandos con sui respectivo traductor
		for s in secs:
			# si la seccion es "SERVIDOR", no hacer caso y continuar con el resto
			if s != "SERVIDOR":
				self.init_printer_traductor(s)


		
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

	def _restartFiscalberry(self):
		"reinicia el servicio fiscalberry"
		from subprocess import call

		resdict = {
				"action": "restartFIscalberry", 
				"rta": call(["service", "fiscalberry-server-rc", "restart"])
				}

		return resdict


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
		global traductores
		resdict = {"action": "getStatus", "rta":{}}
		for tradu in traductores:
			if traductores[tradu]:
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



	def manejar_socket_error(self, err, jsonTicket, traductor):
		print(format(err))
		traductor.comando.conector.driver.reconnect()
		#volver a intententar el mismo comando
		try:
			rta["rta"] = traductor.run( jsonTicket )
		except Exception:
			# ok, no quiere conectar, continuar sin hacer nada
			print("No hay caso, probe de reconectar pero no se pudo")

	def _systemPowerOff(self):
		import commands
		commands.getoutput('halt -h -i -p')
		
	def _systemReboot(self):
		import commands
		commands.getoutput('reboot')

	def json_to_comando	( self, jsonTicket ):
		""" leer y procesar una factura en formato JSON
		"""
		global traductores
		logging.info("Iniciando procesamiento de json...")

		print jsonTicket

		
		rta = {"rta":""}
		# seleccionar impresora
		# esto se debe ejecutar antes que cualquier otro comando
		if 'printerName' in jsonTicket:
			printerName = jsonTicket.pop('printerName')
			traductor = traductores.get( printerName )
			if traductor:
				if traductor.comando.conector is not None:
					try:
						rta["rta"] = traductor.run( jsonTicket )
					except socket.error as err:
						self.manejar_socket_error(err, jsonTicket, traductor)

				else:
					logging.info("el Driver no esta inicializado para la impresora %s"%printerName)
			else:
				raise TraductorException("En el archivo de configuracion no existe la impresora: '%s'"%printerName)
		
		# aciones de comando genericos de Ststus y control
		elif 'powerOff' in jsonTicket:
			rta["rta"] =  self._systemPowerOff()
			
		elif 'osReboot' in jsonTicket:
			rta["rta"] =  self._systemReboot()

		elif 'getStatus' in jsonTicket:
			rta["rta"] =  self._getStatus()

		elif 'restart' in jsonTicket:
			rta["rta"] =  self._restartFiscalberry()

		elif 'getAvaliablePrinters' in jsonTicket:
			rta["rta"] =  self._getAvaliablePrinters()

		elif 'configure' in jsonTicket:
			rta["rta"] =  self._configure(**jsonTicket["configure"])

		else:
			rta["err"] = "No se paso un comando de accion generico ni el nombre de la impresora printerName"

		return rta
