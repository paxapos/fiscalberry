import asyncio
import json
import logging
from Traductores.TraductoresHandler import TraductoresHandler, TraductorException
from Configberry import Configberry
import socketio

logger = logging.getLogger(__name__)

class SioClientHandler():

    def __init__(self):

        self.serverUrl = Configberry.config.get("SERVIDOR","sio_host")
        self.serverPort = Configberry.config.get("SERVIDOR","sio_port")
        self.uuid = Configberry.config.get("SERVIDOR","uuid")
        self.password = Configberry.config.get("SERVIDOR","sio_password")
        self.traductor = TraductoresHandler(self)        
        

    def startSioClient(self):
        sio = socketio.Client(logger=logger)

        def on_comando(comando):
            traductor = self.traductor
            response = {}
            logger.info(f"Request \n -> {comando}")
            try:
                if isinstance(comando, str):
                    jsonMes = json.loads(comando, strict=False)
                else:
                    jsonMes = comando
                response = asyncio.run(traductor.json_to_comando(jsonMes))
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
            except Exception as e:
                errtxt = repr(e) + "- " + str(e)
                logger.exception(errtxt)
                response["err"] = errtxt
    
            logger.info("Response \n <- %s" % response)
            sio.emit('response', response)
        
        @sio.event
        def connect():
            print(self.uuid)
            

        @sio.event
        def disconnect():
            pass

        @sio.event
        def command(msg):
            print(msg)
            on_comando(msg)


        try:
            url = f"http://{self.serverUrl}:{self.serverPort}"
            sio.connect(url = url, socketio_path = "/socket.io/", headers = {"X_UUID":self.uuid, "X_PWD": self.password})
        except Exception as e:
            logging.getLogger("Client").error(f"Error {e}")
        sio.wait()
