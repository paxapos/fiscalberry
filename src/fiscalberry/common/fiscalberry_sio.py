import threading
import socketio
import queue
import os
import time
from fiscalberry.common.ComandosHandler import ComandosHandler, TraductorException
from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler
from fiscalberry.common.live_log_stream import get_live_log_stream_manager
from fiscalberry.version import VERSION


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
            # Verificación TLS configurable (backends con CA privada como dev2).
            # engineio/socketio aceptan ssl_verify como bool; si hay ca_bundle (str) la
            # verificación de polling usa el sistema, así que en ese caso dejamos True.
            _verify = Configberry().get_ssl_verify()
            ssl_verify = _verify if isinstance(_verify, bool) else True
            if ssl_verify is False:
                logger.warning("SocketIO: verificación TLS DESACTIVADA (verify_ssl=false)")
                try:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                except Exception:
                    pass

            self.sio = socketio.Client(
                reconnection=True,
                reconnection_attempts=0,
                reconnection_delay=1,  # Reducido para reconexión más rápida
                reconnection_delay_max=10,  # Reducido para reconexión más rápida
                logger=sioLogger,
                engineio_logger=False,
                ssl_verify=ssl_verify,
            )
            logger.debug("Cliente SocketIO creado exitosamente")
            
            self.stop_event = threading.Event()
            self.thread = None
            self.config = Configberry()
            self.message_queue = queue.Queue()
            # Serializa/coalesce los start_rabbit: evita que dos eventos concurrentes
            # lancen dos configure_and_restart compitiendo por el _thread del handler.
            self._start_rabbit_lock = threading.Lock()

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
            logger.debug(f"SocketIO conectado (SID: {self.sio.sid})")

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

        @self.sio.on("paxaprinter:logs:start", namespace=ns)
        def start_live_logs(data):
            if not isinstance(data, dict) or data.get("uuid") != self.uuid:
                return
            tenant = self.config.get("Paxaprinter", "tenant", fallback="") or ""
            get_live_log_stream_manager().start_session(
                session_id=data.get("sessionId"),
                tenant=tenant,
                uuid=self.uuid,
                publisher=self.rabbit_handler.publish_message,
                expires_at=data.get("expiresAt"),
                min_level=data.get("minLevel", "DEBUG"),
                snapshot_lines=data.get("snapshotLines", 200),
            )

        @self.sio.on("paxaprinter:logs:renew", namespace=ns)
        def renew_live_logs(data):
            if not isinstance(data, dict) or data.get("uuid") != self.uuid:
                return
            get_live_log_stream_manager().renew_session(
                data.get("sessionId"), data.get("expiresAt")
            )

        @self.sio.on("paxaprinter:logs:stop", namespace=ns)
        def stop_live_logs(data):
            if not isinstance(data, dict) or data.get("uuid") != self.uuid:
                return
            get_live_log_stream_manager().stop_session(data.get("sessionId"))

        @self.sio.event(namespace=ns)
        def adopt(data):
            """Eliminar de configberry la info de la seccion paxaprinter"""
            logger.info("Evento adopt recibido")
            try:
                self.rabbit_handler.stop()
                self.config.delete_section("Paxaprinter")
                logger.debug("Adopt: RabbitMQ detenido, config limpiada")
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
            logger.debug("Evento start_rabbit recibido")
            # El backend reenvía start_rabbit en CADA (re)conexión de Socket.IO con las mismas
            # credenciales del broker. Si ya hay una reconfiguración en vuelo, no lanzamos otra:
            # la que corre ya deja el consumer conectado, y dos configure_and_restart a la vez
            # compiten por el _thread del handler (singleton) sin lock. Si las credenciales
            # llegaran a rotar, el próximo start_rabbit (sin reconfig en curso) las aplica.
            with self._start_rabbit_lock:
                if self.rabbitmq_thread and self.rabbitmq_thread.is_alive():
                    logger.debug("start_rabbit ignorado: reconfiguración de RabbitMQ ya en curso")
                    return
                try:
                    # En un hilo aparte y SIN join(): configure_and_restart hace stop()+start()
                    # del consumer (puede tardar varios segundos). Bloquear acá congelaría el
                    # loop de eventos de Socket.IO (no se procesarían command/disconnect/etc.).
                    self.rabbitmq_thread = threading.Thread(
                        target=self.rabbit_handler.configure_and_restart,
                        args=(cfg, self.message_queue),
                        daemon=True
                    )
                    self.rabbitmq_thread.start()
                    logger.info("RabbitMQ (re)configurándose en segundo plano")
                except Exception as e:
                    logger.error(f"Error iniciando RabbitMQ: {e}")
            
    def isRabbitMQRunning(self):
        """
        Estado real del consumer MQTT.

        OJO: NO usar self.rabbitmq_thread, que corre configure_and_restart y muere
        enseguida tras lanzar el consumer real (vive en RabbitMQProcessHandler._thread).
        Delegamos en el handler, que reporta hilo vivo + conexión MQTT efectiva.
        """
        try:
            return self.rabbit_handler.is_running()
        except Exception:
            return False
    
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
            logger.debug(f"SIO run: {self.server_url}")
            self.sio.connect(
                self.server_url,
                namespaces=self.namespaces,
                headers={
                    'x-uuid': self.uuid,
                    'x-version': VERSION,
                },
            )
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
        logger.debug("SIO STOP")
        self.stop_event.set()
        get_live_log_stream_manager().stop_all_sessions()
        try:
            self.sio.disconnect() # detenemios socketio
            self.rabbit_handler.stop() # detenemos RabbitMQ también
        except Exception as e:
            logger.error("Error al desconectar SIO o detener RabbitMQ: %s", e)
        finally:
            logger.debug("SIO y RabbitMQ disconnected OK")
            
        if self.thread and self.thread.is_alive():
            logger.info(f"SIO es STILL LIVE!! no deberia, Waiting for SIO thread to stop, timeout={timeout} seconds.")
            self.thread.join(timeout)
            if self.thread.is_alive():
                logger.debug(f"SIO thread did not stop within the timeout period of {timeout} seconds.")
        self.thread = None
        
        if self.rabbitmq_thread and self.rabbitmq_thread.is_alive():
            logger.info(f"RabbitMQ thread is STILL LIVE!! no deberia, Waiting for RabbitMQ thread to stop, timeout={timeout} seconds.")
            self.rabbitmq_thread.join(timeout)
            if self.rabbitmq_thread.is_alive():
                logger.warning(f"RabbitMQ thread did not stop within the timeout period of {timeout} seconds.")
        self.rabbitmq_thread = None
        logger.debug("SIO y RabbitMQ disconnected OK")
        
        return True