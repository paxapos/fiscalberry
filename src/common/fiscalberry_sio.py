import time
import threading
import socketio
import sys
from common.ComandosHandler import ComandosHandler, TraductorException
from common.fiscalberry_logger import getLogger
import os
from common.Configberry import Configberry


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
        
        self.configberry = Configberry()


        @self.sio.event(namespace='/paxaprinter')
        def connect():
            logger.info(f"connection established with sid {self.sio.sid}")


        @self.sio.event(namespace='/paxaprinter')
        def connect_error(err):
            logger.error(f"Connection failed due to: {err}")

        @self.sio.event(namespace='/paxaprinter')
        def disconnect():
            logger.info("Disconnected from server")
            
        @self.sio.event(namespace='/paxaprinter')
        def error(err):
            logger.error(f"Error recibido: {err}")
            
            
        @self.sio.event(namespace='/paxaprinter')
        def start_rabbit(data: dict):
            ''' viene este json 
            
                export interface HiDto {
                    'RabbitMq': {
                        'host': string,
                        'port': string,
                        'user': string,
                        'password': string,
                        'vhost': string,
                        'queue': string,
                    }
                }

            '''

            rabbitMq = data.get('RabbitMq', None)
            if not rabbitMq:
                logger.error("No se recibio la data esperada")
                return
            
            
            host = rabbitMq['host']
            port = rabbitMq['port']
            user = rabbitMq['user']
            password = rabbitMq['password']
            vhost = rabbitMq['vhost']
            queue = rabbitMq['queue']

            currHost = self.configberry.get("RabbitMq", "host")
            currPort = self.configberry.get("RabbitMq", "port")
            currUser = self.configberry.get("RabbitMq", "user")
            currPass = self.configberry.get("RabbitMq", "password")
            currVhost = self.configberry.get("RabbitMq", "vhost")
            currQueue = self.configberry.get("RabbitMq", "queue")
            
            # si hay cambios guardar
            if currHost != host or currPort != port or currUser != user or currPass != password or currVhost != vhost or currQueue != queue:
                self.configberry.set("RabbitMq", data['RabbitMq'])
            
            if not self.stop_event.is_set():
                self.startRabbit(host, port, user, password, self.uuid)

    def startRabbit(self, host, port, user, password, queue):
        
        def doStart(host, port, user, password, queue):
            from common.rabbit_mq_consumer import RabbitMQConsumer
            
            rb = RabbitMQConsumer(host, port, user, password, queue)
            # Inside the while loop
            rb.start()
            logger.warning("Termino ejecucion de server socketio?.. reconectando en 5s")


        rabbit_thread = threading.Thread(target=doStart, args=(host, port, user, password, queue))
        
        rabbit_thread.start()
        rabbit_thread.join()

    def start_only_status(self):
        self.__run()
        
        
    def start_only_status_in_thread(self) -> threading.Thread:
        self.thread = threading.Thread(target=self.start_only_status)
        self.thread.start()
        return self.thread
        
    def __run(self):
        try:
            logger.info("FiscalberrySio: ******************************* CONECTANDO *******************************")
            self.sio.connect(self.sockeiIoServer, namespaces=self.namespaces, headers={"x-uuid":self.uuid})
            logger.info("Iniciado SioClient en %s con uuid %s" % (self.sockeiIoServer, self.uuid))
            self.sio.wait()

        except socketio.exceptions.ConnectionError as e:
            logger.error(f"socketio Connection error: {e}")
            self.sio.disconnect()
        except Exception as e:
            self.sio.disconnect()
            logger.error(f"An unexpected error occurred: {e}")


    def start_print_server(self):
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


