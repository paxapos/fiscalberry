import time
import threading
import socketio
import sys
from common.ComandosHandler import ComandosHandler, TraductorException
from common.fiscalberry_logger import getLogger
import os

# Configuro logger según ambiente
environment = os.getenv('ENVIRONMENT', 'production')
if environment == 'development':
    sioLogger = True
else:
    sioLogger = False
    

logger = getLogger()




class FiscalberrySio():
    
    sio = None
    sockeiIoServer = None
    uuid = None
    namespaces = None
    
    thread = None
    
    
    
    # Crear un evento de parada
    stop_event = threading.Event()
    
    def __init__(self, sockeiIoServer, uuid, namespaces = ["/paxaprinter"]) -> None:
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=2, reconnection_delay_max=15, logger=sioLogger, engineio_logger=False)
        
        self.sockeiIoServer = sockeiIoServer
        self.uuid = uuid
        self.namespaces = namespaces

        @self.sio.on("connect", namespace='/paxaprinter')
        def handleConnect(**kwargs):
            def handleJoin(*args, **kwargs):
                print(f"Joined!!!!!!!! OKK {args} {kwargs}")

            logger.info(f"connection established with sid {self.sio.sid}")
            self.sio.emit("join", data=uuid, namespace='/paxaprinter', callback=handleJoin)



        @self.sio.on('disconnect', namespace='*')
        def handleDisconnect():
            logger.info("Disconnected from server")
            sys.exit(0)

    def start_only_status(self):
        self.__run()
        
        
    def start_only_status_in_thread(self) -> threading.Thread:
        self.thread = threading.Thread(target=self.start_only_status)
        self.thread.start()
        return self.thread
        
    def __run(self):
        while not self.stop_event.is_set():
            try:
                self.sio.connect(self.sockeiIoServer, namespaces=self.namespaces, headers={"X_UUID":self.uuid})
                logger.info("Iniciado SioClient en %s con uuid %s" % (self.sockeiIoServer, self.uuid))
                self.sio.wait()

            except socketio.exceptions.ConnectionError as e:
                logger.error(f"socketio Connection error: {e}")
                self.sio.disconnect()
            except Exception as e:
                self.sio.disconnect()
                logger.error(f"An unexpected error occurred: {e}")
        
        logger.info("FiscalberrySio: stopped, reconectando en 3s")
        for i in range(3, 0, -1):
            time.sleep(1)
            logger.info(f"FiscalberrySio: stopped, reconectando en {i}s")
        


    def start_print_server(self):
        @self.sio.on('command', namespace='/paxaprinter')
        def handle_command(data):
            logger.debug(f"message received with {data}")
            comandoHandler = ComandosHandler()
            return comandoHandler.send_command(data)
        
        self.__run()
        

    def start_in_thread(self) -> threading.Thread:
        self.thread = threading.Thread(target=self.start_print_server)
        self.thread.start()
        return self.thread
    
    def stop(self):
        self.stop_event.set()
        self.sio.disconnect()
        self.thread.join()
        logger.info("FiscalberrySio: stopped")


