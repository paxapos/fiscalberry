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

from threading import Timer


import ConfigParser


from Traductores.TraductoresHandler import TraductoresHandler, CONFIG_FILE_NAME, TraductorException

MAX_WAIT_SECONDS_BEFORE_SHUTDOWN = 2
INTERVALO_IMPRESORA_WARNING = 10.0

# thread timer para hacer broadcast cuando hay mensaje de la impresora
timerPrinterWarnings = None

# leer los parametros de configuracion de la impresora fiscal 
# en config.ini 
traductor = TraductoresHandler()


class WebSocketException(Exception):
	pass

 
class WSHandler(tornado.websocket.WebSocketHandler):

	def open(self):
		clients.append(self)
		print 'new connection'
	
	def on_message(self, message):
		global traductor
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
		clients.remove(self)
		print 'connection closed'
 
	def check_origin(self, origin):
		return True



 
application = tornado.web.Application([
	(r'/ws', WSHandler),
])

http_server = tornado.httpserver.HTTPServer(application)
clients = []


def broadcast_clientes(message):
	"envia un broadcast a todos los clientes"
	msg = json.dumps( {"msg":message} )
	for cli in clients:
		cli.write_message( msg )

def send_printer_warnings():
    "enviar un broadcast a los clientes con los warnings de impresora, si existen"
    global traductor
    global timerPrinterWarnings

    warns = traductor.getWarnings()
    if warns:
    	broadcast_clientes(warns)  
    #volver a comprobar segun intervalo seleccionado  
    timerPrinterWarnings = Timer(INTERVALO_IMPRESORA_WARNING, send_printer_warnings)
    timerPrinterWarnings.start()









def sig_handler(sig, frame):
	logging.info('Caught signal: %s', sig)
	tornado.ioloop.IOLoop.instance().add_callback(shutdown)


def shutdown():
	logging.info('Stopping http server')
	global http_server
	global timerPrinterWarnings

	if timerPrinterWarnings:
		timerPrinterWarnings.cancel()
		
	http_server.stop()

	logging.info('Will shutdown in %s seconds ...', MAX_WAIT_SECONDS_BEFORE_SHUTDOWN)
	io_loop = tornado.ioloop.IOLoop.instance()

	deadline = time.time() + MAX_WAIT_SECONDS_BEFORE_SHUTDOWN

	def stop_loop():
		now = time.time()
		if now < deadline and (io_loop._callbacks or io_loop._timeouts):
			io_loop.add_timeout(now + 1, stop_loop)
		else:
			io_loop.stop()
			logging.info('Shutdown')

	stop_loop()

def get_list_of_configured_printers(config):
	"Listar las impresoras configuradas"
	# el primer indice del array corresponde a info del SERVER,
	# por eso lo omito. El resto son todas impresoras configuradas
	printers = config.sections()[1:]
	return printers


def get_config_port(config):
	"lee el puerto configurado por donde escuchará el servidor de websockets"	
	puerto = config.get('SERVIDOR', "puerto")
	return puerto

def start_ws_server():
	global http_server
	global timerPrinterWarnings

	
	config = ConfigParser.RawConfigParser()
	print "Reading config file: "+CONFIG_FILE_NAME
	config.read(CONFIG_FILE_NAME)
	
	puerto = get_config_port(config)
	printers = get_list_of_configured_printers(config)

	if len(printers) > 1:
		print "Hay %s impresoras disponibles" % len(printers)
	else:
		print "Impresora disponible:"
	for printer in printers:
		print "  - %s" % printer
		modelo = None
		marca = config.get(printer, "marca")
		driver = config.get(printer, "driver")
		if config.has_option(printer, "modelo"):
			modelo = config.get(printer, "modelo")
		print "      marca: %s, driver: %s" % (marca, driver)
	print "\n"
	

	
	http_server.listen( puerto )
	myIP = socket.gethostbyname(socket.gethostname())



	signal.signal(signal.SIGTERM, sig_handler)
	signal.signal(signal.SIGINT, sig_handler)


	# inicializar intervalo para verificar que la impresora tenga papel
	timerPrinterWarnings = Timer(INTERVALO_IMPRESORA_WARNING, send_printer_warnings).start()


	print '*** Websocket Server Started at %s port %s***' % (myIP, puerto)
	tornado.ioloop.IOLoop.instance().start()

	print "Bye!"
	logging.info("Exit...")


if __name__ == "__main__":
	start_ws_server()