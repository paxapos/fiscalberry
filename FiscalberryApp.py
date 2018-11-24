from tornado import gen
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
from threading import Timer
from Traductores.TraductoresHandler import TraductoresHandler, TraductorException
import sys
import socket
import os
import json
import logging
import logging.config
import time
import ssl
import Configberry
import git

import FiscalberryDiscover
from  tornado import web
if sys.platform == 'win32':
    from signal import signal, SIG_DFL, SIGTERM, SIGINT
else:
    from signal import signal, SIGPIPE, SIG_DFL, SIGTERM, SIGINT
    signal(SIGPIPE,SIG_DFL)
#API
from ApiRest.ApiRestHandler import ApiRestHandler, AuthHandler

MAX_WAIT_SECONDS_BEFORE_SHUTDOWN = 2

# leer los parametros de configuracion de la impresora fiscal
# en config.ini

root = os.path.dirname(os.path.abspath(__file__))


logging.config.fileConfig(root+'/logging.ini')
logger = logging.getLogger(__name__)

class WebSocketException(Exception):
    pass


class PageHandler(tornado.web.RequestHandler):
    def get(self):
        try:
            with open(os.path.join(root + "/js_browser_client", 'example_ws_client.html')) as f:
                self.write(f.read())
        except IOError as e:
            self.write("404: Not Found")

# inicializar intervalo para verificar que la impresora tenga papel
#		

class WSHandler(tornado.websocket.WebSocketHandler):
    def initialize(self, ref_object):
        self.fbApp = ref_object
        self.clients = []
        self.traductor = TraductoresHandler(self, self.fbApp)

    def open(self):
        self.clients.append(self)
        logger.info( 'new connection' )

    def on_message(self, message):
        traductor = self.traductor
        response = {}
        logger.info("----- - -- - - - ---")
        logger.info(message)
        try:
            jsonMes = json.loads(message, strict=False)
            response = traductor.json_to_comando(jsonMes)
        except TypeError, e:
            errtxt = "Error parseando el JSON %s" % e
            logger.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)
        except TraductorException, e:
            errtxt = "Traductor Comandos: %s" % str(e)
            logger.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)
        except KeyError as e:
            errtxt = "El comando no es valido para ese tipo de impresora: %s" % e
            logger.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)
        except socket.error as err:
            import errno
            errtxt = "Socket error: %s" % err
            logger.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)
        except Exception, e:
            errtxt = repr(e) + "- " + str(e)
            logger.error(errtxt)
            response["err"] = errtxt
            import sys, traceback
            traceback.print_exc(file=sys.stdout)

        self.write_message(response)

    def on_close(self):
        self.clients.remove(self)
        logger.info('connection closed')

    def check_origin(self, origin):
        return True


class FiscalberryApp:
    application = None
    http_server = None
    https_server = None

    # thread timer para hacer broadcast cuando hay mensaje de la impresora
    timerPrinterWarnings = None

    def __init__(self):
        logger.info("Preparando Fiscalberry Server")

        newpath = os.path.dirname(os.path.realpath(__file__))
        os.chdir(newpath)

        self.configberry = Configberry.Configberry()

        # actualizar ip privada por si cambio
        ip = self.get_ip()
        self.configberry.writeSectionWithKwargs('SERVIDOR', {'ip_privada': ip})
        logger.info("La IP privada es %s" % ip)


        # evento para terminar ejecucion mediante CTRL+C
        def sig_handler(sig, frame):
            logger.info('Caught signal: %s', sig)
            tornado.ioloop.IOLoop.instance().add_callback(self.shutdown)

        signal(SIGTERM, sig_handler)
        signal(SIGINT, sig_handler)       

    def restart_service(self):
        self.shutdown()
        # self.upgradeGitPull()
        self.discover()
        self.start()

    def shutdown(self):
        logger.info('Stopping http server')

        #logger.info('Will shutdown in %s seconds ...', MAX_WAIT_SECONDS_BEFORE_SHUTDOWN)
        io_loop = tornado.ioloop.IOLoop.current()

        #deadline = time.time() + MAX_WAIT_SECONDS_BEFORE_SHUTDOWN

        io_loop.stop()
        logger.info('Shutdown')

    def upgradeGitPull(self):
        path = os.path.realpath(__file__)
        g = git.cmd.Git( os.path.dirname( path ) )
        
        return g.pull()

    def discover(self):
        # send discover data to your server if the is no URL configured, so nothing will be sent
        if self.configberry.config.has_option('SERVIDOR', "discover_url"):
            fbdiscover = FiscalberryDiscover.send(self.configberry);

    def start(self):
        logger.info("Iniciando Fiscalberry Server")
        settings = {  
            "autoreload": True          
        }

        self.application = tornado.web.Application([
            (r'/wss', WSHandler, {"ref_object" : self}),
            (r'/ws', WSHandler, {"ref_object" : self}),
            (r'/api', ApiRestHandler),
            (r'/api/auth', AuthHandler),
            (r'/', PageHandler),
            (r"/(.*)", web.StaticFileHandler, dict(path=root + "/js_browser_client")),
        ], **settings)

        # cuando cambia el config.ini levanta devuelta el servidor tronado
        tornado.autoreload.watch("config.ini")

        myIP = socket.gethostbyname(socket.gethostname())

        self.http_server = tornado.httpserver.HTTPServer(self.application)
        puerto = self.configberry.config.get('SERVIDOR', "puerto")
        self.http_server.listen(puerto)
        logger.info('*** Websocket Server Started as HTTP at %s port %s***' % (myIP, puerto))


        hasCrt = self.configberry.config.has_option('SERVIDOR', "ssl_crt_path")
        hasKey = self.configberry.config.has_option('SERVIDOR', "ssl_key_path")

        if (hasCrt and hasKey):
            ssl_crt_path = self.configberry.config.get('SERVIDOR', "ssl_crt_path")
            ssl_key_path = self.configberry.config.get('SERVIDOR', "ssl_key_path")
            if ( ssl_crt_path and ssl_key_path ):
                self.https_server = tornado.httpserver.HTTPServer(self.application, ssl_options=
                    {
                        "certfile": ssl_crt_path,
                        "keyfile": ssl_key_path,
                    })
                puerto = int(puerto) + 1
                self.https_server.listen(puerto)
                logger.info('*** Websocket Server Started as HTTPS at %s port %s***' % (myIP, puerto))

        self.print_printers_resume()
       

        tornado.ioloop.IOLoop.current().start()
        tornado.ioloop.IOLoop.current().close()

        logger.info("Bye!")

    def get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def print_printers_resume(self):

        printers = self.configberry.sections()[1:]

        if len(printers) > 1:
            logger.info("Hay %s impresoras disponibles" % len(printers))
        else:
            logger.info("Impresora disponible:")
        for printer in printers:
            logger.info("  - %s" % printer)
            modelo = None
            marca = self.configberry.config.get(printer, "marca")
            driver = "default"
            if self.configberry.config.has_option(printer, "driver"):
                driver = self.configberry.config.get(printer, "driver")
            if self.configberry.config.has_option(printer, "modelo"):
                modelo = self.configberry.config.get(printer, "modelo")
            logger.info("      marca: %s, driver: %s" % (marca, driver))
