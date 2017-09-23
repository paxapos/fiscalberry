from tornado import gen
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
from threading import Timer
from Traductores.TraductoresHandler import TraductoresHandler, TraductorException
import socket
import os
import json
import logging
import time
import ssl
import Configberry
import FiscalberryDiscover
from  tornado import web
import signal

MAX_WAIT_SECONDS_BEFORE_SHUTDOWN = 2
INTERVALO_IMPRESORA_WARNING = 30.0


# leer los parametros de configuracion de la impresora fiscal 
# en config.ini 

root = os.path.dirname(__file__)



class WebSocketException(Exception):
	pass



class PageHandler(tornado.web.RequestHandler):
	def get(self):
		try:
			with open(os.path.join(root+"/js_browser_client", 'example_ws_client.html')) as f:
				self.write(f.read())
		except IOError as e:
			self.write("404: Not Found")
   



# inicializar intervalo para verificar que la impresora tenga papel
#		
 
class WSHandler(tornado.websocket.WebSocketHandler):

	def initialize(self):
		self.clients = []

		self.traductor = TraductoresHandler()

		tornado.ioloop.IOLoop.current().spawn_callback(self.send_printer_warnings, self.clients)


	def open(self):
		self.clients.append(self)
		print 'new connection'
	
	def on_message(self, message):
		traductor = self.traductor
		print("----- - -- - - - ---")
		print message
		try:
			jsonMes = json.loads(message, strict=False)
			response = traductor.json_to_comando( jsonMes )
			self.write_message( response )
		except TypeError:
			response = {"err": "Error parseando el JSON"}
		except TraductorException, e:
			response = {"err": "Traductor Comandos: %s"%str(e)}
		except Exception, e:
			response = {"err": repr(e)+"- "+str(e)}
			import sys, traceback
			traceback.print_exc(file=sys.stdout)
	

	def __procesarImpresoraEterna(self, clients):
	    warns = self.traductor.getWarnings()
	    if warns:
			print warns
	    	# envia broadcast a todos los clientes
			msg = json.dumps( {"msg": warns } )
			for cli in clients:
				cli.write_message( msg )


	@gen.coroutine
	def send_printer_warnings( self, clients ):
		while True:
			yield self.__procesarImpresoraEterna(clients)
			yield gen.sleep(INTERVALO_IMPRESORA_WARNING)


	def on_close(self):
		self.clients.remove(self)
		print 'connection closed'
 
	def check_origin(self, origin):
		return True




class FiscalberryApp:
	application = None
	http_server = None

	# thread timer para hacer broadcast cuando hay mensaje de la impresora
	timerPrinterWarnings = None


	def __init__(self):
		print("Iniciando Fiscalberry Server")

		def sig_handler(sig, frame):
			logging.info('Caught signal: %s', sig)
			tornado.ioloop.IOLoop.instance().add_callback(self.shutdown)

		newpath = os.path.dirname(os.path.realpath(__file__))
		os.chdir(newpath)		
		signal.signal(signal.SIGTERM, sig_handler)
		signal.signal(signal.SIGINT, sig_handler)

		
		self.start()


	@gen.coroutine		
	def shutdown(self):
		logging.info('Stopping http server')

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

		yield stop_loop()



	def start( self ):

		self.application = tornado.web.Application([
			(r'/ws', WSHandler),
			(r'/', PageHandler),
			(r"/(.*)", web.StaticFileHandler, dict(path=root+"/js_browser_client")),
		])


		self.configberry = Configberry.Configberry()

		# send discover data to your server if the is no URL configured, so nothing will be sent
		discoverUrl = self.configberry.config.has_option('SERVIDOR', "discover_url")
		if discoverUrl:
			discoverUrl = self.configberry.config.get('SERVIDOR', "discover_url")
			fbdiscover = FiscalberryDiscover.send(discoverUrl);


		
		hasCrt = self.configberry.config.has_option('SERVIDOR', "ssl_crt_path")
		hasKey = self.configberry.config.has_option('SERVIDOR', "ssl_key_path")


		self.http_server = tornado.httpserver.HTTPServer(self.application)

		self.https_server = None
		if ( hasCrt and hasKey):
			ssl_crt_path = self.configberry.config.get('SERVIDOR', "ssl_crt_path")
			ssl_key_path = self.configberry.config.get('SERVIDOR', "ssl_key_path")
			context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
			context.load_cert_chain(certfile=ssl_crt_path, keyfile=ssl_key_path)

			self.https_server = tornado.httpserver.HTTPServer(self.application, ssl_options=context)
			


		self.print_printers_resume()
		myIP = socket.gethostbyname(socket.gethostname())
		
		puerto = self.configberry.config.get('SERVIDOR', "puerto")
		self.http_server.bind( puerto )
		self.http_server.start()
		print '*** Websocket Server Started as HTTP at %s port %s***' % (myIP, puerto)

		if self.https_server:
			puerto = int(puerto)+1
			self.https_server.bind( puerto )
			self.https_server.start()
			print '*** Websocket Server Started as HTTPS at %s port %s***' % (myIP, puerto )

		# tornado.ioloop.IOLoop.instance().start()
		tornado.ioloop.IOLoop.current().start()

		print "Bye!"
		logging.info("Exit...")
			



	def print_printers_resume(self):
		
		printers = self.configberry.sections()[1:]

		if len(printers) > 1:
			print "Hay %s impresoras disponibles" % len(printers)
		else:
			print "Impresora disponible:"
		for printer in printers:
			print "  - %s" % printer
			modelo = None
			marca = self.configberry.config.get(printer, "marca")
			driver = self.configberry.config.get(printer, "driver")
			if self.configberry.config.has_option(printer, "modelo"):
				modelo = self.configberry.config.get(printer, "modelo")
			print "      marca: %s, driver: %s" % (marca, driver)
		print "\n"
