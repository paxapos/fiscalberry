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
        # Credenciales activas del RabbitMQ Consumer
        self.active_credentials = None
        self._initialized = True

    def get_active_rabbitmq_credentials(self):
        """Retorna las credenciales activas del RabbitMQ Consumer."""
        return self.active_credentials
    
    def _update_active_credentials(self, host, port, user, password, vhost="/"):
        """Actualiza las credenciales activas."""
        self.active_credentials = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'vhost': vhost
        }

    def start(self, message_queue):
        """Arranca el consumidor en un hilo daemon (no bloqueante)."""
        if self._thread and self._thread.is_alive():
            logger.warning("RabbitMQ thread ya en ejecución.")
            return

        host = self.config.get("RabbitMq", "host")
        port = self.config.get("RabbitMq", "port")
        user = self.config.get("RabbitMq", "user")
        password = self.config.get("RabbitMq", "password")
        
        # Actualizar credenciales activas
        self._update_active_credentials(host, port, user, password)
        
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
        
        LÓGICA ABSOLUTA: config.ini NUNCA se sobrescribe.
        Solo se usan valores de SocketIO para campos que estén vacíos en config.ini.
        Si config.ini tiene valores, esos se usan y NO se escriben en disco de nuevo.
        """
        rabbit_cfg = data.get('RabbitMq', {})
        
        logger.info("")
        logger.info("█" * 80)
        logger.info("█" + " " * 78 + "█")
        logger.info("█" + "  PROCESANDO CONFIGURACIÓN RABBITMQ - PRIORIDAD ABSOLUTA: config.ini".ljust(78) + "█")
        logger.info("█" + " " * 78 + "█")
        logger.info("█" * 80)
        logger.info("")
        
        # Leer valores actuales de config.ini
        curr_host = self.config.get("RabbitMq", "host", fallback="")
        curr_port = self.config.get("RabbitMq", "port", fallback="")
        curr_user = self.config.get("RabbitMq", "user", fallback="")
        curr_pwd = self.config.get("RabbitMq", "password", fallback="")
        curr_vhost = self.config.get("RabbitMq", "vhost", fallback="")
        curr_queue = self.config.get("RabbitMq", "queue", fallback="")
        
        logger.info("📂 Valores actuales en config.ini:")
        logger.info(f"   host: '{curr_host}' {' (vacío)' if not curr_host or not str(curr_host).strip() else ' ✓'}")
        logger.info(f"   port: '{curr_port}' {' (vacío)' if not curr_port or not str(curr_port).strip() else ' ✓'}")
        logger.info(f"   user: '{curr_user}' {' (vacío)' if not curr_user or not str(curr_user).strip() else ' ✓'}")
        logger.info(f"   password: {'(vacío)' if not curr_pwd or not str(curr_pwd).strip() else '****** ✓'}")
        logger.info(f"   vhost: '{curr_vhost}' {' (vacío)' if not curr_vhost or not str(curr_vhost).strip() else ' ✓'}")
        logger.info(f"   queue: '{curr_queue}' {' (vacío)' if not curr_queue or not str(curr_queue).strip() else ' ✓'}")
        logger.info("")
        logger.info("🌐 Valores disponibles desde SocketIO:")
        logger.info(f"   host: {rabbit_cfg.get('host', 'N/A')}")
        logger.info(f"   port: {rabbit_cfg.get('port', 'N/A')}")
        logger.info(f"   user: {rabbit_cfg.get('user', 'N/A')}")
        logger.info(f"   password: {'******' if rabbit_cfg.get('password') else 'N/A'}")
        logger.info(f"   vhost: {rabbit_cfg.get('vhost', 'N/A')}")
        logger.info(f"   queue: {rabbit_cfg.get('queue', 'N/A')}")
        logger.info("")
        logger.info("⚙️  DECISIÓN FINAL (qué se usará):")
        logger.info("-" * 80)
        
        # Solo usar SocketIO para rellenar campos vacíos (NUNCA sobrescribir)
        updates = {}
        final_config = {}
        
        # HOST
        if not curr_host or not str(curr_host).strip():
            new_host = rabbit_cfg.get("host", "")
            if new_host:
                updates["host"] = new_host
                final_config["host"] = new_host
                logger.warning(f"   ➤ host: config.ini VACÍO → rellenando desde SocketIO: '{new_host}'")
            else:
                final_config["host"] = ""
                logger.error(f"   ➤ host: config.ini VACÍO y SocketIO sin valor → quedará vacío ⚠️")
        else:
            final_config["host"] = curr_host
            logger.info(f"   ✓ host: usando config.ini (PROTEGIDO) → '{curr_host}'")
            
        # PORT
        if not curr_port or not str(curr_port).strip():
            new_port = rabbit_cfg.get("port", "5672")
            if new_port:
                updates["port"] = new_port
                final_config["port"] = new_port
                logger.warning(f"   ➤ port: config.ini VACÍO → rellenando desde SocketIO: '{new_port}'")
            else:
                final_config["port"] = "5672"
                logger.warning(f"   ➤ port: config.ini VACÍO → usando default: '5672'")
        else:
            final_config["port"] = curr_port
            logger.info(f"   ✓ port: usando config.ini (PROTEGIDO) → '{curr_port}'")
            
        # USER
        if not curr_user or not str(curr_user).strip():
            new_user = rabbit_cfg.get("user", "guest")
            if new_user:
                updates["user"] = new_user
                final_config["user"] = new_user
                logger.warning(f"   ➤ user: config.ini VACÍO → rellenando desde SocketIO: '{new_user}'")
            else:
                final_config["user"] = "guest"
                logger.warning(f"   ➤ user: config.ini VACÍO → usando default: 'guest'")
        else:
            final_config["user"] = curr_user
            logger.info(f"   ✓ user: usando config.ini (PROTEGIDO) → '{curr_user}'")
            
        # PASSWORD
        if not curr_pwd or not str(curr_pwd).strip():
            new_pwd = rabbit_cfg.get("password", "guest")
            if new_pwd:
                updates["password"] = new_pwd
                final_config["password"] = new_pwd
                logger.warning(f"   ➤ password: config.ini VACÍO → rellenando desde SocketIO: '******'")
            else:
                final_config["password"] = "guest"
                logger.warning(f"   ➤ password: config.ini VACÍO → usando default: '******'")
        else:
            final_config["password"] = curr_pwd
            logger.info(f"   ✓ password: usando config.ini (PROTEGIDO) → '******'")
            
        # VHOST
        if not curr_vhost or not str(curr_vhost).strip():
            new_vhost = rabbit_cfg.get("vhost", "/")
            if new_vhost:
                updates["vhost"] = new_vhost
                final_config["vhost"] = new_vhost
                logger.warning(f"   ➤ vhost: config.ini VACÍO → rellenando desde SocketIO: '{new_vhost}'")
            else:
                final_config["vhost"] = "/"
                logger.warning(f"   ➤ vhost: config.ini VACÍO → usando default: '/'")
        else:
            final_config["vhost"] = curr_vhost
            logger.info(f"   ✓ vhost: usando config.ini (PROTEGIDO) → '{curr_vhost}'")
            
        # QUEUE
        if not curr_queue or not str(curr_queue).strip():
            new_queue = rabbit_cfg.get("queue", "")
            if new_queue:
                updates["queue"] = new_queue
                final_config["queue"] = new_queue
                logger.warning(f"   ➤ queue: config.ini VACÍO → rellenando desde SocketIO: '{new_queue}'")
            else:
                final_config["queue"] = ""
                logger.error(f"   ➤ queue: config.ini VACÍO y SocketIO sin valor → quedará vacío ⚠️")
        else:
            final_config["queue"] = curr_queue
            logger.info(f"   ✓ queue: usando config.ini (PROTEGIDO) → '{curr_queue}'")
        
        # Resumen final
        logger.info("-" * 80)
        logger.info("")
        logger.info("🎯 CONFIGURACIÓN FINAL QUE SE USARÁ PARA CONECTAR:")
        logger.info(f"   🔗 Servidor: {final_config['host']}:{final_config['port']}")
        logger.info(f"   👤 Usuario: {final_config['user']}")
        logger.info(f"   🏠 VHost: {final_config['vhost']}")
        logger.info(f"   📬 Cola: {final_config['queue']}")
        logger.info("")
        
        # SOLO escribir en config.ini si había campos vacíos que rellenamos
        if updates:
            self.config.set("RabbitMq", updates)
            logger.warning(f"💾 Guardando campos rellenados en config.ini: {list(updates.keys())}")
            logger.warning("   Estos valores ahora quedarán PROTEGIDOS y no se sobrescribirán")
        else:
            logger.info("✅ config.ini ya está completo - NO se modificó nada")
        
        logger.info("")
        logger.info("█" * 80)
        logger.info("")
            
        # Hacer lo mismo con Paxaprinter - solo rellenar campos vacíos
        pax_cfg = data.get('Paxaprinter', {})
        pax_updates = {}
        
        curr_alias = self.config.get("Paxaprinter", "alias", fallback="")
        curr_tenant = self.config.get("Paxaprinter", "tenant", fallback="")
        curr_site = self.config.get("Paxaprinter", "site_name", fallback="")
        
        if not curr_alias or not str(curr_alias).strip():
            if pax_cfg.get('alias'):
                pax_updates["alias"] = pax_cfg.get('alias')
        if not curr_tenant or not str(curr_tenant).strip():
            if pax_cfg.get('tenant'):
                pax_updates["tenant"] = pax_cfg.get('tenant')
        if not curr_site or not str(curr_site).strip():
            if pax_cfg.get('site_name'):
                pax_updates["site_name"] = pax_cfg.get('site_name')
                
        if pax_updates:
            self.config.set("Paxaprinter", pax_updates)
            logger.info(f"Paxaprinter: campos vacíos rellenados: {list(pax_updates.keys())}")

        # Reinicia hilo con la configuración actual de config.ini
        if self._thread and self._thread.is_alive():
            self.stop(timeout=5)
        self.start(message_queue)