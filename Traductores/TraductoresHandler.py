# coding=utf-8

import json
import Configberry
import logging
import importlib
import socket
import threading
import tornado.ioloop


INTERVALO_IMPRESORA_WARNING = 30.0


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

class TraductorException(Exception):
	pass

class TraductoresHandler:
	"""Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""

	traductores = {}

	config = Configberry.Configberry()
	webSocket = None


	def __init__(self, webSocket):
		self.webSocket = webSocket



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

			traductor = self.__init_printer_traductor(printerName)

			if traductor:
				if traductor.comando.conector is not None:
					try:
						rta["rta"] = traductor.run( jsonTicket )
					except KeyError as e:
						rta["err"] = "El comando no es válido para ese tipo de impresora: %s"%e
						logging.error("El comando no es válido para ese tipo de impresora: %s"%e)	
					except socket.error as err:
						self.__manejar_socket_error(err, jsonTicket, traductor)
						logging.error("Socket error: %s"%err)
					except Exception as e:
						rta["err"] = "Error inesperado: %s"%e
						logging.error("Error inesperado: %s"%e)	
				else:
					rta["err"] = "el Driver no esta inicializado para la impresora %s"%printerName
					logging.error("el Driver no esta inicializado para la impresora %s"%printerName)
			else:
				rta["err"] = "En el archivo de configuracion no existe la impresora: '%s'"%printerName
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
		collect_warnings = {}
		for trad in self.traductores:
			if self.traductores[trad]:
				warn = self.traductores[trad].comando.getWarnings()
				if warn:
					collect_warnings[trad] = warn
		return collect_warnings

	def __getDeviceData(self, device_list):
		import nmap

		return_dict = {}  # lo retornado

		device_list_len = len(device_list)
		device_list_identifier_pos = device_list_len - 1
		index = 0
		separator = 'abcdefghijklmnopqrstuvwxyz'

		logging.info('Iniciando la busqueda por nmap')
		
		nm = nmap.PortScanner()
		nm.scan('-sP 192.168.1.0/24')  # parametros a nmap, se pueden mejorar mucho

		if device_list[device_list_identifier_pos] == 0:

			device_list.pop(device_list_identifier_pos)

			for h in nm.all_hosts():
				if 'mac' in nm[h]['addresses']:
							for x in device_list: 
								if x in nm[h]['addresses']['mac']:
									return_dict[nm[h]['vendor'][nm[h]['addresses']['mac']]+'_'+separator[index]] = {'host' : nm[h]['addresses']['ipv4'], 'marca' : 'EscP', 'driver' : 'ReceiptDirectJet'}
									index += 1
			print(return_dict)
			logging.info('Finalizó la busqueda por nmap')
		 	return return_dict

		elif device_list[device_list_identifier_pos] == 1:

			device_list.pop(device_list_identifier_pos)

			for h in nm.all_hosts():
						 if 'mac' in nm[h]['addresses']:

								for x in device_list:
									if "vendor" in nm[h]:
										if x in nm[h]['vendor'][nm[h]['addresses']['mac']]:
											return_dict[nm[h]['vendor'][nm[h]['addresses']['mac']]+'_'+separator[index]] = {'host' : nm[h]['addresses']['ipv4'], 'marca' : 'EscP', 'driver' : 'ReceiptDirectJet'}
											index += 1
			print(return_dict)
			logging.info('Finalizó la busqueda por nmap')
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

		


	def __init_printer_traductor(self, printerName):

		dictSectionConf = self.config.get_config_for_printer(printerName)
		marca = dictSectionConf.get("marca")
		del dictSectionConf['marca']
		# instanciar los comandos dinamicamente
		libraryName = "Comandos."+marca+"Comandos"
		comandoModule = importlib.import_module(libraryName)
		comandoClass = getattr(comandoModule, marca+"Comandos")
		
		comando = comandoClass(**dictSectionConf)
		traductorComando = comando.traductor

		return traductorComando




		
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
		#self.__getPrintersAndWriteConfig()

		# la primer seccion corresponde a SERVER, el resto son las impresoras
		rta = {
			"action": "getAvaliablePrinters",
			"rta": self.config.sections()[1:]
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



	def __manejar_socket_error(self, err, jsonTicket, traductor):
		print(format(err))
		traductor.comando.conector.driver.reconnect()
		#volver a intententar el mismo comando
		try:
			rta["rta"] = traductor.run( jsonTicket )
		except Exception:
			# ok, no quiere conectar, continuar sin hacer nada
			print("No hay caso, probe de reconectar pero no se pudo")
			