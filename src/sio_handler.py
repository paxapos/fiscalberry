import asyncio
import json
from Traductores.TraductoresHandler import TraductoresHandler, TraductorException
import socketio
import sys
from fiscalberry_logger import getLogger

sio = socketio.AsyncClient(logger=False, engineio_logger=False)


logger = getLogger()
'''
@sio.event
async def connect_error(data):
    print("The connection failed!")


    
@sio.event
async def disconnect(self):
    print(f"desconectado")
    logger.info("Disconnected from server")
    self.connected = False

@sio.event
async def message(self, data):
    logger.info(f"Message received: {data}")
    
@sio.event
async def command(self, comando):
    response = {}
    logger.info(f"Request \n -> {comando}")
    try:
        if isinstance(comando, str):
            jsonMes = json.loads(comando, strict=False)
        else:
            jsonMes = comando
        traductor = TraductoresHandler()
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
    return response
'''


@sio.on("connect")
def connect():
    print(f"connection established with sid {sio.sid}")

@sio.on('hi', namespace='/paxaprinter')
async def sayhi(event, namespace, sid, data):
    print(f"HI!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! Event {event} - Namespace {namespace} - SID {sid} - Data {data}")
        

@sio.on('*', namespace='*')
async def any_event_any_namespace(event, namespace, sid, data):
    print(f"Event {event} - Namespace {namespace} - SID {sid} - Data {data}")
    

    
async def start(sockeiIoServer, uuid, namespaces = ["/paxaprinter"]):
    try:
        
        await sio.connect(sockeiIoServer, namespaces=namespaces, headers={"X_UUID":uuid})
        
        print("Iniciado SioClient en %s con uuid %s" % (sockeiIoServer, uuid))

        return await sio.wait()
    except Exception as e:
        print(f"Error {e} quedo re cuelgue?=")
        logger.error(f"Error {e}")