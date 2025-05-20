import threading
import socketio
import queue
import os
import time
from fiscalberry.common.ComandosHandler import ComandosHandler, TraductorException
from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler


environment = os.getenv('ENVIRONMENT', 'production')
sioLogger = True if environment == 'development' else False
logger = getLogger()

class FiscalberrySio:
    _instance = None
    _lock = threading.Lock()
    
    rabbitmq_thread = None

    def __new__(cls, *a, **k):
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, server_url: str, uuid: str, namespaces='/paxaprinter', on_message=None):
        if self._initialized:
            return
        self.server_url = server_url
        self.uuid = uuid
        self.namespaces = namespaces
        self.on_message = on_message
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,
            reconnection_delay=2,
            reconnection_delay_max=15,
            logger=True,
            engineio_logger=False,
        )
        self.stop_event = threading.Event()
        self.thread = None
        self.config = Configberry()
        self.message_queue = queue.Queue()
        self.rabbit_handler = RabbitMQProcessHandler()
        self._register_events()
        self._initialized = True

    def _register_events(self):
        ns = self.namespaces

        @self.sio.event(namespace=ns)
        def connect():
            logger.info(f"SIO connect, SID={self.sio.sid}")

        @self.sio.event(namespace=ns)
        def connect_error(err):
            logger.error(f"SIO connect error: {err}")

        @self.sio.event(namespace=ns)
        def disconnect():
            logger.info("SIO disconnect")

        @self.sio.event(namespace=ns)
        def error(err):
            logger.error(f"SIO error: {err}")

        @self.sio.event(namespace=ns)
        def start_sio():
            logger.info("SIO start_sio")

        @self.sio.event(namespace=ns)
        def adopt(data):
            """ eliminar  de configberry la info de  la seccion paxaprinter"""
            logger.info(f"SIO adopt: {data}")
            try:
                # Detener servicio de RabbitMQ
                self.rabbit_handler.stop()
                if self.config.delete_section("Paxaprinter"):
                    logger.info("RabbitMQ service stopped and Paxaprinter section removed")
            except Exception as e:
                logger.error(f"adopt: {e}")
            

        @self.sio.event(namespace=ns)
        def message(data):
            logger.info(f"SIO message: {data}")
            if self.on_message:
                try:
                    self.on_message(data)
                except Exception as e:
                    logger.error(f"on_message callback: {e}")

        @self.sio.event(namespace=ns)
        def command(cfg: dict):
            logger.info(f"Vino evento command {cfg}")

            

        @self.sio.event(namespace=ns)
        def start_rabbit(cfg: dict):
            logger.info(f"start_rabbit: RabbitMQ {cfg}")

            # config + restart, pasamos la cola para tail -f
            # Create and start a daemon thread to run configure_and_restart
            self.rabbitmq_thread = threading.Thread(
                target=self.rabbit_handler.configure_and_restart,
                args=(cfg, self.message_queue),
                daemon=True
            )
            self.rabbitmq_thread.start()
            self.rabbitmq_thread.join()
            
    def isRabbitMQRunning(self):
        """
        Verifica si el hilo de RabbitMQ está en ejecución.
        """
        if self.rabbitmq_thread and self.rabbitmq_thread.is_alive():
            return True
        else:
            return False
        # Si no hay hilo, significa que RabbitMQ no está corriendo
    
    def isSioRunning(self):
        """
        Verifica si el hilo de SIO está en ejecución.
        """
        if self.thread and self.thread.is_alive():
            return True
        else:
            return False
        # Si no hay hilo, significa que SIO no está corriendo

    def _run(self):
        try:
            logger.info(f"SIO run: {self.server_url}")
            self.sio.connect(self.server_url, namespaces=self.namespaces, headers={'x-uuid': self.uuid})
            self.sio.wait()
        except Exception as e:
            logger.error(f"SIO Error al conectar: {e}")
       

    def start(self) -> threading.Thread:
        if self.thread and self.thread.is_alive():
            return self.thread
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
       
        return self.thread

    def stop(self, timeout=2):
        logger.info("SIO STOP")
        self.stop_event.set()
        try:
            self.sio.disconnect() # detenemios socketio
            self.rabbit_handler.stop() # detenemos RabbitMQ también
        except Exception as e:
            logger.error("Error al desconectar SIO o detener RabbitMQ: %s", e)
        finally:
            logger.info("SIO y RabbitMQ disconnected OK")
            
        if self.thread and self.thread.is_alive():
            logger.info(f"SIO es STILL LIVE!! no deberia, Waiting for SIO thread to stop, timeout={timeout} seconds.")
            self.thread.join(timeout)
            if self.thread.is_alive():
                logger.warning(f"SIO thread did not stop within the timeout period of {timeout} seconds.")
        self.thread = None
        
        if self.rabbitmq_thread and self.rabbitmq_thread.is_alive():
            logger.info(f"RabbitMQ thread is STILL LIVE!! no deberia, Waiting for RabbitMQ thread to stop, timeout={timeout} seconds.")
            self.rabbitmq_thread.join(timeout)
            if self.rabbitmq_thread.is_alive():
                logger.warning(f"RabbitMQ thread did not stop within the timeout period of {timeout} seconds.")
        self.rabbitmq_thread = None
        logger.info("SIO y RabbitMQ disconnected OK")
        
        return True