# coding=utf-8

import json
import Configberry
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



# es un diccionario como clave va el nombre de la impresora que funciona como cola
# cada KEY es una printerName y contiene un a instancia de TraductorReceipt o TraductorFiscal dependiendo
# si la impresora es fiscal o receipt
traductores = {}

class TraductorException(Exception):
	pass

class TraductoresHandler:
	"""Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""



	# traductores = {}


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

	config = Configberry.Configberry()


	def __init__(self):
		self.__init_cola_traductores_printer()


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
						self.__manejar_socket_error(err, jsonTicket, traductor)

				else:
					logging.info("el Driver no esta inicializado para la impresora %s"%printerName)
			else:
				raise TraductorException("En el archivo de configuracion no existe la impresora: '%s'"%printerName)
		
		# aciones de comando genericos de Ststus y control
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

	def __getDeviceData(self, device_list):
		import nmap

		return_dict = {}  # lo retornado

		device_list_len = len(device_list)
		device_list_identifier_pos = device_list_len - 1

		nm = nmap.PortScanner()
		nm.scan('-sP 192.168.1.0/24')  # parametros a nmap, se pueden mejorar mucho

		if device_list[device_list_identifier_pos] == 0:

		 device_list.pop(device_list_identifier_pos)

		 for h in nm.all_hosts():
				if 'mac' in nm[h]['addresses']:
							for x in device_list: 
								if x in nm[h]['addresses']['mac']:
									return_dict[nm[h]['vendor'][nm[h]['addresses']['mac']]] = {'host' : nm[h]['addresses']['ipv4'], 'state' : nm[h]['status']['state'], 'mac' : nm[h]['addresses']['mac'], 'marca' : 'EscP', 'modelo' : '', 'driver' : 'ReceiptDirectJet'}
									
		 return return_dict

		elif device_list[device_list_identifier_pos] == 1:

			device_list.pop(device_list_identifier_pos)

			for h in nm.all_hosts():
						 if 'mac' in nm[h]['addresses']:

								for x in device_list:
										if x in nm[h]['vendor'][nm[h]['addresses']['mac']]:
												return_dict[nm[h]['vendor'][nm[h]['addresses']['mac']]] = {'host' : nm[h]['addresses']['ipv4'], 'state' : nm[h]['status']['state'], 'mac' : nm[h]['addresses']['mac'], 'marca' : 'EscP', 'modelo' : '', 'driver' : 'ReceiptDirectJet'}
			return return_dict  
				
		else:
			 print 'identificador erroneo'
			 quit()


	def __getPrintersAndWriteConfig(self):
		vendors = ['Bematech', 1]  # vendors // 1 as vendor identifier
		macs = ['00:07:25',0]  # macs // 0 as mac identifier

		printer = self.__getDeviceData(macs)

		i = 0
		for printerName in printer:
			listadoNames = printer.keys()
			printerName = listadoNames[i]
			listadoItems = printer.values()

			kwargs = printer[printerName] #Items de la impresora
			self.config.writeSectionWithKwargs(printerName, kwargs)
			i +=1
		return 1

	def __init_keep_looking_for_device_connected(self):
		def recorrer_traductores_y_comprobar():
			global traductores
			logging.info("Iniciando procesamiento de json...")
			for t in traductores:
				print "estoy por verificando conexion de %s"%t
				if not traductores[t].comando.conector:
					print "*** NO conectada"
					logging.info("la impresora %s esta desconectada y voy a reintentar conectarla"%t)
					self.__init_printer_traductor(t)
				else:
					print "ya estaba conectado"

		set_interval(recorrer_traductores_y_comprobar, 10)



	


	def __init_printer_traductor(self, printerName):
		global traductores
		dictSectionConf = self.config.get_config_for_printer(printerName)
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

		secs = self.config.sections()

		# para cada impresora le voy a crear su juego de comandos con sui respectivo traductor
		for s in secs:
			# si la seccion es "SERVIDOR", no hacer caso y continuar con el resto
			if s != "SERVIDOR":
				self.__init_printer_traductor(s)


		
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

		self.config.writeSectionWithKwargs(printerName, kwargs)

		return {
			"action": "configure",
			"rta": "ok"
		}

	def _getAvaliablePrinters(self):	
		#Esta función llama a otra que busca impresoras. Luego se encarga de escribir el config.ini con las impresoras encontradas.
		self.__getPrintersAndWriteConfig()

		# la primer seccion corresponde a SERVER, el resto son las impresoras
		rta = {
			"action": "getAvaliablePrinters",
			"rta": self.config.sections()[1:]
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



	def __manejar_socket_error(self, err, jsonTicket, traductor):
		print(format(err))
		traductor.comando.conector.driver.reconnect()
		#volver a intententar el mismo comando
		try:
			rta["rta"] = traductor.run( jsonTicket )
		except Exception:
			# ok, no quiere conectar, continuar sin hacer nada
			print("No hay caso, probe de reconectar pero no se pudo")
			