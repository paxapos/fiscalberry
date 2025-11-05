import threading
import socket
import time
import logging
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.rabbitmq.consumer import RabbitMQConsumer
import pika.exceptions

logger = logging.getLogger(__name__)

class RabbitMQProcessHandler:
    """Administra el hilo de RabbitMQConsumer: arranque, paro y reintentos."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._thread = None
        self._stop_event = threading.Event()
        self.config = Configberry()
        self._initialized = True

    def start(self, message_queue):
        """Arranca el consumidor en un hilo daemon (no bloqueante)."""
        if self._thread and self._thread.is_alive():
            logger.warning("RabbitMQ thread ya en ejecución.")
            return

        host = self.config.get("RabbitMq", "host")
        port = self.config.get("RabbitMq", "port")
        user = self.config.get("RabbitMq", "user")
        password = self.config.get("RabbitMq", "password")
        
        # TODO deberia usarse esto: queue_name = self.config.get("RabbitMq", "queue")
        queue_name = self.config.get("SERVIDOR", "uuid")
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_consumer,
            args=(host, port, user, password, queue_name, message_queue),
            daemon=True
        )
        self._thread.start()
        logger.info("RabbitMQ thread iniciado.")

    def _check_network_connectivity(self, host, port, timeout=5):
        """Verifica la conectividad de red básica antes de intentar conectar con RabbitMQ."""
        try:
            # Primero verificar resolución DNS
            socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            
            # Luego verificar si el puerto está abierto
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except socket.gaierror as e:
            logger.error(f"Error de resolución DNS para {host}: {e}")
            return False
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            logger.error(f"No se puede conectar a {host}:{port} - {e}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado verificando conectividad: {e}")
            return False

    def _run_consumer(self, host, port, user, password, queue_name, message_queue):
        """Loop de conexión/reconexión al servidor RabbitMQ con backoff exponencial."""
        retry_count = 0
        max_retries_before_backoff = 3
        base_delay = 5  # segundos
        max_delay = 300  # 5 minutos máximo
        
        while not self._stop_event.is_set():
            try:
                # Verificar conectividad básica antes de intentar conexión RabbitMQ
                if not self._check_network_connectivity(host, int(port)):
                    retry_count += 1
                    logger.warning(f"Conectividad de red falló para {host}:{port}")
                    self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
                    continue
                
                consumer = RabbitMQConsumer(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    queue_name=queue_name,
                    message_queue=message_queue
                )
                consumer.start()
                # Si llegamos aquí, la conexión fue exitosa, resetear contador
                retry_count = 0
                logger.info("Conexión RabbitMQ establecida exitosamente")
                # consumer.start() sólo retorna al desconectarse o error.
            except socket.gaierror as ex:
                retry_count += 1
                logger.error(f"Error de resolución DNS para '{host}': {ex}")
                logger.error("Posibles soluciones:")
                logger.error("1. Verificar que el hostname 'rabbitmq' esté configurado correctamente")
                logger.error("2. Verificar conectividad de red")
                logger.error("3. Verificar que el servidor RabbitMQ esté ejecutándose")
                logger.error("4. Considerar usar una IP directa en lugar del hostname")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
            except pika.exceptions.AMQPConnectionError as ex:
                retry_count += 1
                logger.error(f"Error de conexión AMQP a {host}:{port}: {ex}")
                logger.error("Verificar que el servidor RabbitMQ esté ejecutándose y accesible")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
            except pika.exceptions.ProbableAuthenticationError as ex:
                retry_count += 1
                logger.error(f"Error de autenticación con RabbitMQ: {ex}")
                logger.error(f"Verificar credenciales - Usuario: {user}, VHost: {self.config.get('RabbitMq', 'vhost', '/')}")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
            except pika.exceptions.ProbableAccessDeniedError as ex:
                retry_count += 1
                logger.error(f"Acceso denegado a RabbitMQ: {ex}")
                logger.error(f"Verificar permisos del usuario '{user}' en vhost '{self.config.get('RabbitMq', 'vhost', '/')}'")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
            except ConnectionError as ex:
                retry_count += 1
                logger.error(f"Error de conexión de red a {host}:{port}: {ex}")
                logger.error("Verificar conectividad de red y que el puerto esté abierto")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
            except Exception as ex:
                retry_count += 1
                logger.error(f"Error inesperado en RabbitMQConsumer: {ex}", exc_info=True)
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
                
        logger.info("Salida del bucle de RabbitMQProcessHandler.")
    
    def _handle_retry(self, retry_count, max_retries_before_backoff, base_delay, max_delay):
        """Maneja la lógica de reintento con backoff exponencial."""
        if self._stop_event.is_set():
            return
            
        if retry_count <= max_retries_before_backoff:
            delay = base_delay
            logger.warning(f"Reintento {retry_count}/{max_retries_before_backoff} - esperando {delay}s antes del siguiente intento...")
        else:
            # Backoff exponencial después de los primeros reintentos
            delay = min(base_delay * (2 ** (retry_count - max_retries_before_backoff)), max_delay)
            logger.warning(f"Reintento {retry_count} con backoff exponencial - esperando {delay}s antes del siguiente intento...")
            
        # Esperar con verificación periódica del stop_event
        for _ in range(int(delay)):
            if self._stop_event.is_set():
                break
            time.sleep(1)

    def stop(self, timeout: float = 1):
        """Detiene el hilo y espera su finalización."""
        if self._thread and self._thread.is_alive():
            logger.info("Deteniendo RabbitMQConsumer...")
            self._stop_event.set()
            self._thread.join(timeout)
            if self._thread.is_alive():
                logger.warning("RabbitMQConsumer no se detuvo a tiempo.")
            else:
                logger.info("RabbitMQConsumer detenido correctamente.")
        else:
            logger.warning("No hay hilo de RabbitMQConsumer en ejecución.")
        self._thread = None
        self._stop_event.clear()
        logger.info("RabbitMQProcessHandler detenido.")

    def configure_and_restart(self, data: dict, message_queue):
        """
        Recibe el JSON, actualiza Configberry si cambia y reinicia el hilo.
        data debe traer keys 'RabbitMq' y 'Paxaprinter' como en tu interfaz HiDto.
        
        LÓGICA: Para cada campo, si tiene contenido en config.ini, usar ese valor.
        Solo usar valores de SocketIO para completar campos vacíos en config.
        """
        rabbit_cfg = data.get('RabbitMq', {})
        
        def get_config_or_message_value(config_key, message_key, default_value=""):
            """
            Obtiene valor del config.ini si existe y no está vacío, sino del mensaje SocketIO.
            Prioridad: config.ini -> mensaje SocketIO -> valor por defecto
            """
            config_value = self.config.get("RabbitMq", config_key, fallback="")
            if config_value and str(config_value).strip():
                logger.info(f"{config_key}: usando config.ini -> {config_value}")
                return config_value
            else:
                message_value = rabbit_cfg.get(message_key, default_value)
                logger.info(f"{config_key}: config.ini vacío, usando SocketIO -> {message_value}")
                return message_value
        
        logger.info("=== Configuración RabbitMQ - Prioridad config.ini ===")
        
        # Aplicar la lógica a todos los parámetros
        host = get_config_or_message_value("host", "host")
        port_str = get_config_or_message_value("port", "port", "5672")
        user = get_config_or_message_value("user", "user", "guest")
        pwd = get_config_or_message_value("password", "password", "guest")
        vhost = get_config_or_message_value("vhost", "vhost", "/")
        queue = get_config_or_message_value("queue", "queue", "")
        
        # Convertir puerto a entero
        try:
            port = int(port_str)
        except (ValueError, TypeError):
            logger.warning(f"Puerto inválido '{port_str}', usando 5672 por defecto")
            port = 5672
        
        # compara con lo actual
        curr = {
            "host": self.config.get("RabbitMq", "host"),
            "port": self.config.get("RabbitMq", "port"),
            "user": self.config.get("RabbitMq", "user"),
            "password": self.config.get("RabbitMq", "password"),
            "vhost": self.config.get("RabbitMq", "vhost"),
            "queue": self.config.get("RabbitMq", "queue"),
        }
        new = {"host": host, "port": port, "user": user, "password": pwd, "vhost": vhost, "queue": queue}
        
        # Verificar si hay cambios en la configuración
        if curr != new:
            self.config.set("RabbitMq", new)
            logger.info("Configuración de RabbitMQ actualizada en disk con valores prioritarios del config.ini")
        else:
            logger.info("Configuración de RabbitMQ sin cambios")
            
        # compara con lo actual de Paxaprinter
        pax_cfg = data.get('Paxaprinter', {})
        alias = pax_cfg.get('alias')
        tenant = pax_cfg.get('tenant')
        site_name = pax_cfg.get('site_name')
        curr_pax = {
            "alias": self.config.get("Paxaprinter", "alias"),
            "tenant": self.config.get("Paxaprinter", "tenant"),
            "site_name": self.config.get("Paxaprinter", "site_name")
        }
        new_pax = {"alias": alias, "tenant": tenant, "site_name": site_name}
        if curr_pax != new_pax:
            self.config.set("Paxaprinter", new_pax)
            logger.info("Configuración de Paxaprinter actualizada en disk.")

        # guarda en config y reinicia hilo
        if self._thread and self._thread.is_alive():
            self.stop(timeout=5)
        self.start(message_queue)