#!/usr/bin/env python
# coding=utf-8

import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
import socket
import json
import signal
import logging
import time
import os.path
from threading import Timer
from Traductores.TraductoresHandler import TraductoresHandler, CONFIG_FILE_NAME, TraductorException
import ConfigParser






# chdir otherwise will not work fine in rc service
newpath = os.path.dirname(os.path.realpath(__file__))
os.chdir(newpath)




MAX_WAIT_SECONDS_BEFORE_SHUTDOWN = 2
INTERVALO_IMPRESORA_WARNING = 30.0

#global para el listado de clientes conectados
clients = []
# leer los parametros de configuracion de la impresora fiscal 
# en config.ini 
traductor = TraductoresHandler()

class WebSocketException(Exception):
	pass

 
class WSHandler(tornado.websocket.WebSocketHandler):

	def open(self):
		global clients
		clients.append(self)
		print 'new connection'
	
	def on_message(self, message):
		global traductor
		print message
		try:
			jsonMes = json.loads(message.decode('utf-8'), strict=False)
			response = traductor.json_to_comando( jsonMes )
		except TypeError:
			print "error parseando el JSON "
			print jsonMes
			response = {"err": "Error parseando el JSON"}
		except TraductorException, e:
			response = {"err": "Traductor Comandos: %s"%str(e)}
		except Exception, e:
			response = {"err": repr(e)+"- "+str(e)}

			import sys, traceback
			traceback.print_exc(file=sys.stdout)

		print response
		self.write_message( response )
 
	def on_close(self):
		global clients
		clients.remove(self)
		print 'connection closed'
 
	def check_origin(self, origin):
		return True




class FiscalberryServer:
	application = None
	http_server = None

	# thread timer para hacer broadcast cuando hay mensaje de la impresora
	timerPrinterWarnings = None


	def __init__(self):

		self.http_server = tornado.web.Application([
			(r'/ws', WSHandler),
		])
		

		self.config = ConfigParser.RawConfigParser()
		print "Reading config file: "+CONFIG_FILE_NAME
		self.config.read(CONFIG_FILE_NAME)


	def shutdown(self):
		logging.info('Stopping http server')

		logging.info('Will shutdown in %s seconds ...', MAX_WAIT_SECONDS_BEFORE_SHUTDOWN)
		io_loop = tornado.ioloop.IOLoop.instance()

		deadline = time.time() + MAX_WAIT_SECONDS_BEFORE_SHUTDOWN

		if self.timerPrinterWarnings:
			self.timerPrinterWarnings.cancel()

		def stop_loop():
			now = time.time()
			if now < deadline and (io_loop._callbacks or io_loop._timeouts):
				io_loop.add_timeout(now + 1, stop_loop)
			else:
				io_loop.stop()
				logging.info('Shutdown')

		stop_loop()



	def start( self ):

		self.print_printers_resume()
		puerto = self.get_config_port()
		self.http_server.listen( puerto )
		myIP = socket.gethostbyname(socket.gethostname())

		# inicializar intervalo para verificar que la impresora tenga papel
		timerPrinterWarnings = Timer(INTERVALO_IMPRESORA_WARNING, self.send_printer_warnings).start()

		print '*** Websocket Server Started at %s port %s***' % (myIP, puerto)
		tornado.ioloop.IOLoop.instance().start()

		print "Bye!"
		logging.info("Exit...")
			

		

	def get_config_port(self):
		"lee el puerto configurado por donde escuchará el servidor de websockets"
		
		puerto = self.config.get('SERVIDOR', "puerto")
		return puerto




	def get_list_of_configured_printers( self ):
		"Listar las impresoras configuradas"
		# el primer indice del array corresponde a info del SERVER,
		# por eso lo omito. El resto son todas impresoras configuradas
		printers = self.config.sections()[1:]
		return printers



	def send_printer_warnings( self ):
	    "enviar un broadcast a los clientes con los warnings de impresora, si existen"
	    global clients
	    global traductor

	    warns = traductor.getWarnings()
	    if warns:
			print warns
	    	# envia broadcast a todos los clientes
			msg = json.dumps( {"msg": warns } )
			for cli in clients:
				cli.write_message( msg )
	    #volver a comprobar segun intervalo seleccionado  
	    self.timerPrinterWarnings = Timer(INTERVALO_IMPRESORA_WARNING, self.send_printer_warnings)
	    self.timerPrinterWarnings.start()




	def print_printers_resume(self):
		printers = self.get_list_of_configured_printers()

		if len(printers) > 1:
			print "Hay %s impresoras disponibles" % len(printers)
		else:
			print "Impresora disponible:"
		for printer in printers:
			print "  - %s" % printer
			modelo = None
			marca = self.config.get(printer, "marca")
			driver = self.config.get(printer, "driver")
			if self.config.has_option(printer, "modelo"):
				modelo = self.config.get(printer, "modelo")
			print "      marca: %s, driver: %s" % (marca, driver)
		print "\n"
		


		







if __name__ == "__main__":

	fbserver = FiscalberryServer()

	def sig_handler(sig, frame):
		logging.info('Caught signal: %s', sig)
		tornado.ioloop.IOLoop.instance().add_callback(fbserver.shutdown)


	signal.signal(signal.SIGTERM, sig_handler)
	signal.signal(signal.SIGINT, sig_handler)

	fbserver.start()
	#start_ws_server()