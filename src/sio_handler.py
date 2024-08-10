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
async 
'''

async def send_command(comando):
    response = {}
    logger.info(f"Request \n -> {comando}")
    try:
        if isinstance(comando, str):
            jsonMes = json.loads(comando, strict=False)
        else:
            jsonMes = comando
        traductor = TraductoresHandler()
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
    except Exception as e:
        errtxt = repr(e) + "- " + str(e)
        logger.exception(errtxt)
        response["err"] = errtxt

    logger.info("Response \n <- %s" % response)
    return response
        

    
async def start(sockeiIoServer, uuid, namespaces = ["/paxaprinter"]):
    
    @sio.on("connect", namespace='/paxaprinter')
    async def handleConnect(**kwargs):
        def handleJoin(*args, **kwargs):
            print(f"Joined!!!!!!!! OKK {args} {kwargs}")
            
            
        print(f"connection established with sid {sio.sid}")
        await sio.emit("join", data=uuid, namespace='/paxaprinter', callback=handleJoin)


    @sio.on('hi', namespace='*')
    async def any_event_any_namespace( *kargs, **kwargs):
        print(f"Any event in any namespace {kargs}")
        
    @sio.on('disconnect', namespace='*')
    async def handleDisconnect():
        print("Disconnected")
        logger.info("Disconnected from server")
        sys.exit(0)
        
    @sio.on('command', namespace='/paxaprinter')
    async def handle_command(data):
        print(f"message received with {data}")
        return await send_command(data)
    
        
    try:
        await sio.connect(sockeiIoServer, namespaces=namespaces, headers={"X_UUID":uuid})
        print("Iniciado SioClient en %s con uuid %s" % (sockeiIoServer, uuid))
        return await sio.wait()
    except socketio.exceptions.ConnectionError as e:
        print(f"socketio Connection error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
