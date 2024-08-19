import asyncio
import json
from Traductores.TraductoresHandler import TraductoresHandler, TraductorException
import socketio
import sys
from fiscalberry_logger import getLogger

sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=2, logger=False, engineio_logger=False)


logger = getLogger()


def send_command(comando):
    response = {}
    logger.info(f"Request \n -> {comando}")
    try:
        if isinstance(comando, str):
            jsonMes = json.loads(comando, strict=False)
        else:
            jsonMes = comando
        traductor = TraductoresHandler()
        response = traductor.json_to_comando(jsonMes)
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
        

    
def start(sockeiIoServer, uuid, namespaces = ["/paxaprinter"]):
    
    @sio.on("connect", namespace='/paxaprinter')
    def handleConnect(**kwargs):
        def handleJoin(*args, **kwargs):
            print(f"Joined!!!!!!!! OKK {args} {kwargs}")

        print(f"connection established with sid {sio.sid}")
        sio.emit("join", data=uuid, namespace='/paxaprinter', callback=handleJoin)


    @sio.on('hi', namespace='*')
    def any_event_any_namespace( *kargs, **kwargs):
        print(f"Any event in any namespace {kargs}")

    @sio.on('disconnect', namespace='*')
    def handleDisconnect():
        print("Disconnected")
        logger.info("Disconnected from server")
        sys.exit(0)

    @sio.on('command', namespace='/paxaprinter')
    def handle_command(data):
        print(f"message received with {data}")
        return send_command(data)


    try:
        sio.connect(sockeiIoServer, namespaces=namespaces, headers={"X_UUID":uuid})
        print("Iniciado SioClient en %s con uuid %s" % (sockeiIoServer, uuid))
        return sio.wait()
    except socketio.exceptions.ConnectionError as e:
        print(f"socketio Connection error: {e}")
        sio.disconnect()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        sio.disconnect()

