import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
import socket
import json

import ConfigParser
from Traductor import Traductor, CONFIG_FILE_NAME


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
 
 
if __name__ == "__main__":
	config = ConfigParser.RawConfigParser()
	print CONFIG_FILE_NAME
	config.read(CONFIG_FILE_NAME)
	puerto = config.get('SERVIDOR', "puerto")
	
	http_server = tornado.httpserver.HTTPServer(application)
	http_server.listen( puerto )
	myIP = socket.gethostbyname(socket.gethostname())
	print '*** Websocket Server Started at %s port %s***' % (myIP, puerto)
	tornado.ioloop.IOLoop.instance().start()