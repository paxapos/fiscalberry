import multiprocessing
import socketio
import tornado
from tornado import httpserver, websocket, ioloop, web
from Traductores.TraductoresHandler import TraductoresHandler, TraductorException
import sys
import socket
import os
import json
import logging
import logging.config
import ssl
import Configberry
import FiscalberryDiscover


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


class PageHandler(web.RequestHandler):
    def get(self):
        try:
            with open(os.path.join(root + "/js_browser_client", 'example_ws_client.html')) as f:
                self.write(f.read())
                f.close()
        except IOError as e:
            self.write("404: Not Found")


class WSHandler(websocket.WebSocketHandler):

    def initialize(self, ref_object):
        self.fbApp = ref_object
        self.clients = []
        self.traductor = TraductoresHandler(self, self.fbApp)


    def open(self):
        self.clients.append(self)
        logger.info('Connection Established')


    async def on_message(self, message):
        traductor = self.traductor
        response = {}
        logger.info("Request \n -> %s" % message)
        try:
            jsonMes = json.loads(message, strict=False)
            response = await traductor.json_to_comando(jsonMes)
        except TypeError as e:
            errtxt = "Error parseando el JSON %s" % e
            logger.exception(errtxt)
            response["err"] = errtxt
        except TraductorException as e:
            errtxt = "Traductor Comandos: %s" % str(e)
            logger.exception(errtxt)
            response["err"] = errtxt
        except KeyError as e:
            errtxt = "El comando no es valido para ese tipo de impresora: %s" % e
            logger.exception(errtxt)
            response["err"] = errtxt
        except socket.error as err:
            errtxt = "Socket error: %s" % err
            logger.exception(errtxt)
            response["err"] = errtxt
        except Exception as e:
            errtxt = repr(e) + "- " + str(e)
            logger.exception(errtxt)
            response["err"] = errtxt

        logger.info("Response \n <- %s" % response)
        self.write_message(response)


    def on_close(self):
        self.clients.remove(self)
        logger.info('Connection Closed')


    def check_origin(self, origin):
        return True


class FiscalberryApp:
    application = None
    http_server = None
    https_server = None

    socketio = None
    sioServerTornadoHandler = None
    sioProcess = None
    sio = None

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
        logger.info(f"La IP privada es {ip}")


        # evento para terminar ejecucion mediante CTRL+C
        def sig_handler(sig, frame):
            logger.info(f'Caught signal: {sig}')
            ioloop.IOLoop.current().add_callback_from_signal(self.shutdown)

        signal(SIGTERM, sig_handler)
        signal(SIGINT, sig_handler)       

    def restart_service(self):
        self.shutdown()
        self.discover()
        self.start()

    def shutdown(self):
        logger.info('Stopping http server')
        io_loop = ioloop.IOLoop.current()
        if self.sioProcess:
            self.sioProcess.join(timeout=3)
        io_loop.stop()
        logger.info('Shutdown')


    def discover(self):
        # send discover data to your server if the is no URL configured, so nothing will be sent
        hasopnURL  = self.configberry.config.has_option('SERVIDOR', "discover_url")
        hasopnUUID = self.configberry.config.has_option('SERVIDOR', "UUID")
        if hasopnURL and hasopnUUID:
            fbdiscover = FiscalberryDiscover.send(self.configberry)


    def start(self, isSioServer = False, isSioClient = False):

        self.isSioServer = isSioServer
        self.isSioClient = isSioClient
        
        self.startSocketIO()

        logger.info("Iniciando Fiscalberry Server")
        settings = {  
            "autoreload": True
        }

        self.application = web.Application([
            
            (r'/socket.io/', self.sioServerTornadoHandler),
            (r'/wss', WSHandler, {"ref_object" : self}),
            (r'/ws', WSHandler, {"ref_object" : self}),
            (r'/api', ApiRestHandler),
            (r'/api/auth', AuthHandler),
            (r'/', PageHandler),
            (r"/(.*)", web.StaticFileHandler, dict(path=root + "/js_browser_client"))

        ], **settings)
        # self.application.add_handlers(r'/socket.io/', socketio.get_tornado_handler(self.sio))

        # cuando cambia el config.ini levanta devuelta el servidor tornado
        tornado.autoreload.watch("config.ini")

        myIP = socket.gethostbyname(socket.gethostname())

        self.http_server = httpserver.HTTPServer(self.application)
        puerto = self.configberry.config.get('SERVIDOR', "puerto")
        self.http_server.listen(puerto)
        logger.info(f'*** Websocket Server Started as HTTP at {myIP} port {puerto} ***')


        hasCrt = self.configberry.config.has_option('SERVIDOR', "ssl_crt_path")
        hasKey = self.configberry.config.has_option('SERVIDOR', "ssl_key_path")

        if (hasCrt and hasKey):
            ssl_crt_path = self.configberry.config.get('SERVIDOR', "ssl_crt_path")
            ssl_key_path = self.configberry.config.get('SERVIDOR', "ssl_key_path")
            if ( ssl_crt_path and ssl_key_path ):
                self.https_server = httpserver.HTTPServer(self.application, ssl_options=
                    {
                        "certfile": ssl_crt_path,
                        "keyfile": ssl_key_path,
                    })
                puerto = int(puerto) + 1
                self.https_server.listen(puerto)
                logger.info(f'*** Websocket Server Started as HTTPS at {myIP} port {puerto} ***')

        self.print_printers_resume()
       
        ioloop.IOLoop.current().start()
        ioloop.IOLoop.current().close()
        if self.sioProcess:
            self.sioProcess.terminate()
        logger.info("Bye!")

    def startSocketIO(self):
        
        if (self.isSioServer and not self.isSioClient): 
            logger.info("Iniciando Socket.io Server")           
            import SioServerHandler
            self.socketio = SioServerHandler
            sio = self.socketio.sio
            self.sioServerTornadoHandler = socketio.get_tornado_handler(sio)
            self.socketio.password = self.configberry.config.get("SERVIDOR", "sio_password", fallback = "password")

        if (self.isSioClient and not self.isSioServer):
            logger.info("Iniciando Socket.io Client")
            from SioClientHandler import SioClientHandler
            self.socketio = SioClientHandler()
            self.sioProcess = multiprocessing.Process(target = self.socketio.startSioClient, args=(self.configberry.config.get("SERVIDOR", "uuid"),), name="SocketIOClient")
            self.sioProcess.start()


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
            logger.info(f"Hay {len(printers)} impresoras disponibles")
        else:
            logger.info("Impresora disponible:")
        for printer in printers:
            logger.info(f"  - {printer}")
            marca = self.configberry.config.get(printer, "marca")
            driver = "default"
            if self.configberry.config.has_option(printer, "driver"):
                driver = self.configberry.config.get(printer, "driver")
            logger.info(f"      marca: {marca}, driver: {driver}")
