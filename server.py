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


import ConfigParser
from Traductor import Traductor, CONFIG_FILE_NAME

MAX_WAIT_SECONDS_BEFORE_SHUTDOWN = 2

class WebSocketException(Exception):
	pass

'''
This is a simple Websocket Echo server that uses the Tornado websocket handler.
Please run `pip install tornado` with python of version 2.7.9 or greater to install tornado.
This program will echo back the reverse of whatever it recieves.
Messages are output to the terminal for debuggin purposes. 
''' 
 
class WSHandler(tornado.websocket.WebSocketHandler):

	def __init__(self, *args, **kwargs):
		
		# leer los parametros de configuracion de la impresora fiscal 
		# en config.ini 
		self.traductor = Traductor('IMPRESORA_FISCAL')
		super(WSHandler, self).__init__(*args, **kwargs)


	def open(self):
		print 'new connection'
	
	def on_message(self, message):
		jsonMes = json.loads(message)
		response = self.traductor.json_to_comando( jsonMes )
		#print response
		if response:
			self.write_message( response )
 
	def on_close(self):
		print 'connection closed'
 
	def check_origin(self, origin):
		return True
 
application = tornado.web.Application([
	(r'/ws', WSHandler),
])




def sig_handler(sig, frame):
	logging.info('Caught signal: %s', sig)
	tornado.ioloop.IOLoop.instance().add_callback(shutdown)


def shutdown():
	logging.info('Stopping http server')
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
		marca = config.get(printer, "marca")
		modelo = config.get(printer, "modelo")
		path = config.get(printer, "path")
		print "      marca: %s, modelo: %s (%s)" % (marca, modelo, path)
	print "\n"
	

	http_server = tornado.httpserver.HTTPServer(application)
	http_server.listen( puerto )
	myIP = socket.gethostbyname(socket.gethostname())


	signal.signal(signal.SIGTERM, sig_handler)
	signal.signal(signal.SIGINT, sig_handler)


	print '*** Websocket Server Started at %s port %s***' % (myIP, puerto)
	tornado.ioloop.IOLoop.instance().start()

	print "Bye!"
	logging.info("Exit...")


if __name__ == "__main__":
	start_ws_server()