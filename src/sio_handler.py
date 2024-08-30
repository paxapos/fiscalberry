import socketio
import sys
from common.ComandosHandler import ComandosHandler, TraductorException
from common.fiscalberry_logger import getLogger

sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=2, logger=False, engineio_logger=False)


logger = getLogger()

    
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
        logger.debug(f"message received with {data}")
        comandoHandler = ComandosHandler()
        return comandoHandler.send_command(data)


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

