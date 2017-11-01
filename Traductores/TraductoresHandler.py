# coding=utf-8

import json
import Configberry
import logging
import importlib
import socket
import threading
import tornado.ioloop
import nmap
import os


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

		traductor = None
		
		rta = {"rta":""}
		# seleccionar impresora
		# esto se debe ejecutar antes que cualquier otro comando
		if 'printerName' in jsonTicket:
			printerName = jsonTicket.pop('printerName')

			traductor = self.__init_printer_traductor(printerName)

			if traductor:
				if traductor.comando.conector is not None:
					rta["rta"] = traductor.run( jsonTicket )
				else:
					raise TraductorException("el Driver no esta inicializado para la impresora %s"%printerName)
			else:
				raise TraductorException("En el archivo de configuracion no existe la impresora: '%s'"%printerName)
		
		# aciones de comando genericos de Ststus y control
		elif 'getStatus' in jsonTicket:
			rta["rta"] =  self._getStatus()

		elif 'restart' in jsonTicket:
			rta["rta"] =  self._restartFiscalberry()

		elif 'findAvaliablePrinters' in jsonTicket:
			self._findAvaliablePrinters()
			rta["rta"] =  self._getAvaliablePrinters()

		elif 'getAvaliablePrinters' in jsonTicket:
			rta["rta"] =  self._getAvaliablePrinters()

		elif 'getPrinterInfo' in jsonTicket:
			rta["rta"] =  self._getPrinterInfo(jsonTicket["getPrinterInfo"])

		elif 'configure' in jsonTicket:
			rta["rta"] =  self._configure(**jsonTicket["configure"])

		else:
			logging.error("No se pasó un comando válido")
			raise TraductorException("No se pasó un comando válido")

		# cerrar el driver
		if traductor and traductor.comando:
			traductor.comando.close()

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

	def __getDeviceData(self):
		# avaliable mac address list
		device_list = [
					'00:0E:C3', # Logic Controls BEMATECH
					'00:07:25', # Bematech
				]  

		avaliablePrinters = []  # lo retornado

		logging.info('Iniciando la busqueda por nmap')
		
		nm = nmap.PortScanner()

		ipPrivada = self.config.config.get('SERVIDOR','ip_privada')
		iplist = ipPrivada.split('.')
		ipBroadcast = iplist[0]+"."+iplist[1]+"."+iplist[2]+".0/24"
		
		ret = nm.scan(hosts=ipBroadcast, arguments='-sP')

		print("Ejecutando comando: nmap "+'-sP '+ipBroadcast)
		print(ret)

		for h in nm.all_hosts():
			if 'mac' in nm[h]['addresses']:
				for x in device_list: 
					if x in nm[h]['addresses']['mac']:
						print(nm[h])
						encontrada = {
										'host' : nm[h]['addresses']['ipv4'], 
										'vendor' : nm[h]['vendor'][ nm[h]['addresses']['mac'] ], 
										'marca' : 'EscP', 
										'driver' : 'ReceiptDirectJet',
										'mac': nm[h]['addresses']['mac']
										}
						avaliablePrinters.append(encontrada)
		logging.info('Finalizó la busqueda por nmap')
	 	return avaliablePrinters



	def __getPrintersAndWriteConfig(self):
		printerlist = self.__getDeviceData()
		for data in printerlist:
			elqueencontro = self.config.findByMac(data['mac'])
			if elqueencontro:
				(s, encontrada) = elqueencontro
				if encontrada:
					print("::::::IMPRESORA ENCONTRADA::::::")
					print(encontrada)
					print("::::::********************::::::")
					encontrada['host'] = data['host']
					data = encontrada
					printerName = s
			else:
				printerName = data['vendor']+"-%s"%data['mac']
				data['marca'] = 'EscP'
				data['driver'] = 'ReceiptDirectJet'
			print("la data es %s"%data)
			self.config.writeSectionWithKwargs(printerName, data)

		


	def __init_printer_traductor(self, printerName):

		dictSectionConf = self.config.get_config_for_printer(printerName)
		marca = dictSectionConf.get("marca")
		del dictSectionConf['marca']
		# instanciar los comandos dinamicamente
		libraryName = "Comandos."+marca+"Comandos"
		comandoModule = importlib.import_module(libraryName)
		comandoClass = getattr(comandoModule, marca+"Comandos")
		
		comando = comandoClass(**dictSectionConf)
		return comando.traductor


		
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

	def _findAvaliablePrinters(self):	
		#Esta función llama a otra que busca impresoras. Luego se encarga de escribir el config.ini con las impresoras encontradas.
		if os.geteuid() != 0:
			print os.geteuid()
			return {"action": "findAvaliablePrinters",
					"rta": "Error, no es superusuario (%s)"%os.geteuid()
					}

		self.__getPrintersAndWriteConfig()


	def _getAvaliablePrinters(self):	

		# la primer seccion corresponde a SERVER, el resto son las impresoras
		rta = {
			"action": "getAvaliablePrinters",
			"rta": self.config.sections()[1:]
		}

		return rta

	def _getPrinterInfo(self, printerName):
		rta = self.config.get_config_for_printer(printerName)
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
			