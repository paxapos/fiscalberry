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
logger = getLogger("SocketIO")

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
    
    @classmethod
    def reset_singleton(cls):
        """
        Resetea el estado del singleton para permitir reinicialización.
        CRÍTICO para Android cuando la app se cierra y reabre.
        """
        with cls._lock:
            if cls._instance:
                # Limpiar stop_event si existe
                if hasattr(cls._instance, 'stop_event'):
                    cls._instance.stop_event.clear()
                # Marcar como no inicializado
                cls._instance._initialized = False
                # Limpiar referencias a threads muertos
                if hasattr(cls._instance, 'thread'):
                    cls._instance.thread = None
                if hasattr(cls._instance, 'rabbitmq_thread'):
                    cls._instance.rabbitmq_thread = None
                # Resetear también RabbitMQ handler
                try:
                    from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler
                    RabbitMQProcessHandler.reset_singleton()
                except Exception:
                    pass

    def __init__(self, server_url: str, uuid: str, namespaces='/paxaprinter', on_message=None):
        if self._initialized:
            logger.debug("FiscalberrySio ya inicializado, saltando...")
            return
            
        logger.info(f"FiscalberrySio: {server_url} ns={namespaces}")
        
        self.server_url = server_url
        self.uuid = uuid
        self.namespaces = namespaces
        self.on_message = on_message
        
        try:
            self.sio = socketio.Client(
                reconnection=True,
                reconnection_attempts=0,
                reconnection_delay=1,  # Reducido para reconexión más rápida
                reconnection_delay_max=10,  # Reducido para reconexión más rápida
                logger=sioLogger,
                engineio_logger=False,
            )
            logger.debug("Cliente SocketIO creado exitosamente")
            
            self.stop_event = threading.Event()
            self.thread = None
            self.config = Configberry()
            self.message_queue = queue.Queue()
            
            self.rabbit_handler = RabbitMQProcessHandler()
            
            self._register_events()
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Error durante inicialización de FiscalberrySio: {e}", exc_info=True)
            raise

    def _register_events(self):
        ns = self.namespaces
        logger.debug(f"Registrando eventos SocketIO para namespace: {ns}")

        @self.sio.event(namespace=ns)
        def connect():
            logger.info(f"SocketIO conectado (SID: {self.sio.sid})")

        @self.sio.event(namespace=ns)
        def connect_error(err):
            logger.error(f"SocketIO error de conexión: {err}")

        @self.sio.event(namespace=ns)
        def disconnect():
            logger.warning("SocketIO desconectado")

        @self.sio.event(namespace=ns)
        def error(err):
            logger.error(f"SocketIO error: {err}")

        @self.sio.event(namespace=ns)
        def start_sio():
            logger.info("Recibido evento start_sio")

        @self.sio.event(namespace=ns)
        def adopt(data):
            """Eliminar de configberry la info de la seccion paxaprinter"""
            logger.info("Evento adopt recibido")
            try:
                self.rabbit_handler.stop()
                self.config.delete_section("Paxaprinter")
                logger.info("Adopt: RabbitMQ detenido, config limpiada")
            except Exception as e:
                logger.error(f"Error en adopt: {e}")
            

        @self.sio.event(namespace=ns)
        def message(data):
            logger.debug(f"Mensaje SocketIO recibido")
            if self.on_message:
                try:
                    self.on_message(data)
                except Exception as e:
                    logger.error(f"Error en on_message: {e}")

        @self.sio.event(namespace=ns)
        def command(cfg: dict):
            logger.debug("Comando SocketIO recibido")
            
            # Procesamiento optimizado de comandos con manejo async
            try:
                # Crear un handler de comandos para procesar
                handler = ComandosHandler()
                
                # Procesar comando de forma no bloqueante
                def process_command():
                    try:
                        start_time = time.time()
                        result = handler.send_command(cfg)
                        processing_time = time.time() - start_time
                        
                        # Log optimizado para comandos lentos
                        if processing_time > 1.0:
                            logger.warning(f"Comando lento procesado en {processing_time:.2f}s")
                        else:
                            logger.debug(f"Comando procesado en {processing_time:.2f}s")
                            
                        # Enviar respuesta de vuelta si es necesario
                        if result and "err" in result:
                            logger.error(f"Error procesando comando: {result['err']}")
                        else:
                            logger.debug("Comando procesado exitosamente")
                            
                    except Exception as e:
                        logger.error(f"Error procesando comando: {e}", exc_info=True)
                
                # Ejecutar en hilo separado para no bloquear SocketIO
                threading.Thread(target=process_command, daemon=True).start()
                
            except Exception as e:
                logger.error(f"Error en manejo de comando SocketIO: {e}", exc_info=True)

        @self.sio.event(namespace=ns)
        def start_rabbit(cfg: dict):
            logger.info("Evento start_rabbit recibido")
            try:
                self.rabbitmq_thread = threading.Thread(
                    target=self.rabbit_handler.configure_and_restart,
                    args=(cfg, self.message_queue),
                    daemon=True
                )
                self.rabbitmq_thread.start()
                self.rabbitmq_thread.join()
                logger.info("RabbitMQ iniciado")
            except Exception as e:
                logger.error(f"Error iniciando RabbitMQ: {e}")
            
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