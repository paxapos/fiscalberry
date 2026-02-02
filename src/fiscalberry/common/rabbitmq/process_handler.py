import threading
import socket
import time
import logging
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.rabbitmq.consumer import RabbitMQConsumer

logger = logging.getLogger(__name__)

class RabbitMQProcessHandler:
    """Administra el hilo del Consumer MQTT: arranque, paro y reintentos."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
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
                if hasattr(cls._instance, '_stop_event'):
                    cls._instance._stop_event.clear()
                # Marcar como no inicializado
                cls._instance._initialized = False
                # Limpiar referencias a threads muertos
                if hasattr(cls._instance, '_thread'):
                    cls._instance._thread = None

    def __init__(self):
        if self._initialized:
            return
        self._thread = None
        self._stop_event = threading.Event()
        self.config = Configberry()
        # Credenciales activas del MQTT Consumer
        self.active_credentials = None
        self._initialized = True

    def get_active_rabbitmq_credentials(self):
        """Retorna las credenciales activas del MQTT Consumer."""
        return self.active_credentials
    
    def _update_active_credentials(self, host, port, user, password, vhost="/"):
        """Actualiza las credenciales activas."""
        self.active_credentials = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'vhost': vhost  # Se mantiene por compatibilidad, pero no se usa en MQTT
        }

    def start(self, message_queue):
        """
        Arranca el consumidor MQTT en un hilo daemon (no bloqueante).
        
        NOTA: user y password vienen de active_credentials (memoria),
        no de config.ini, por seguridad.
        """
        if self._thread and self._thread.is_alive():
            logger.warning("MQTT thread ya en ejecución.")
            return

        # host/port de config
        host = self.config.get("RabbitMq", "host")
        port = self.config.get("RabbitMq", "port")
        
        # Credenciales: primero config.ini, luego memoria (active_credentials) como fallback
        user = None
        password = None
        
        # 1. Primero intentar desde config.ini (tiene prioridad absoluta si está escrito)
        user = self.config.get("RabbitMq", "user", fallback=None)
        password = self.config.get("RabbitMq", "password", fallback=None)
        
        # 2. Fallback: usar memoria (active_credentials de SocketIO) solo si config.ini está vacío
        if (not user or not user.strip()) and self.active_credentials:
            user = self.active_credentials.get('user')
        if (not password or not password.strip()) and self.active_credentials:
            password = self.active_credentials.get('password')
        
        if not user or not password:
            print("\n============================================================")
            print("[ERROR] Credenciales MQTT incompletas")
            print("        (user o password faltante en config.ini y memoria)")
            print("============================================================\n")
            logger.error("Credenciales MQTT incompletas (user o password faltante en config.ini y memoria)")
            return
        
        queue_name = self.config.get("SERVIDOR", "uuid")
        
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_consumer,
            args=(host, port, user, password, queue_name, message_queue),
            daemon=True
        )
        self._thread.start()
        logger.info("MQTT thread iniciado.")

    def _check_network_connectivity(self, host, port, timeout=5):
        """Verifica la conectividad de red básica antes de intentar conectar con MQTT."""
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
        """Loop de conexión/reconexión al broker MQTT con backoff exponencial."""
        retry_count = 0
        max_retries_before_backoff = 3
        base_delay = 5  # segundos
        max_delay = 300  # 5 minutos máximo
        
        while not self._stop_event.is_set():
            try:
                # Verificar conectividad básica antes de intentar conexión MQTT
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
                logger.debug("Conexión MQTT establecida exitosamente")
                # consumer.start() sólo retorna al desconectarse o error.
            except socket.gaierror as ex:
                retry_count += 1
                logger.error(f"Error de resolución DNS para '{host}': {ex}")
                logger.error("Posibles soluciones:")
                logger.error("1. Verificar que el hostname esté configurado correctamente")
                logger.error("2. Verificar conectividad de red")
                logger.error("3. Verificar que el broker MQTT esté ejecutándose")
                logger.error("4. Considerar usar una IP directa en lugar del hostname")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
            except ConnectionError as ex:
                retry_count += 1
                logger.error(f"Error de conexión de red a {host}:{port}: {ex}")
                logger.error("Verificar conectividad de red y que el puerto esté abierto")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
            except Exception as ex:
                retry_count += 1
                logger.error(f"Error inesperado en MQTT Consumer: {ex}", exc_info=True)
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
            logger.debug("Deteniendo MQTT Consumer...")
            self._stop_event.set()
            self._thread.join(timeout)
            if self._thread.is_alive():
                logger.warning("MQTT Consumer no se detuvo a tiempo.")
            else:
                logger.debug("MQTT Consumer detenido correctamente.")
        else:
            logger.warning("No hay hilo de MQTT Consumer en ejecución.")
        self._thread = None
        self._stop_event.clear()
        logger.info("RabbitMQProcessHandler detenido.")

    def configure_and_restart(self, data: dict, message_queue):
        """
        Recibe el JSON, actualiza Configberry si cambia y reinicia el hilo.
        
        LÓGICA ABSOLUTA: config.ini NUNCA se sobrescribe.
        Solo se usan valores de SocketIO para campos que estén vacíos en config.ini.
        """
        rabbit_cfg = data.get('RabbitMq', {})
        
        # Leer valores actuales de config.ini (excepto user/password que son solo memoria)
        curr_host = self.config.get("RabbitMq", "host", fallback="")
        curr_port = self.config.get("RabbitMq", "port", fallback="")
        curr_vhost = self.config.get("RabbitMq", "vhost", fallback="")
        curr_queue = self.config.get("RabbitMq", "queue", fallback="")
        
        # Solo usar SocketIO para rellenar campos vacíos
        updates = {}
        final_config = {}
        
        # HOST
        if not curr_host or not str(curr_host).strip():
            new_host = rabbit_cfg.get("host", "")
            if new_host:
                updates["host"] = new_host
                final_config["host"] = new_host
            else:
                final_config["host"] = ""
        else:
            final_config["host"] = curr_host
            
        # PORT - FORZADO A 1883 (MQTT) PARA v3.0.x
        # DESARROLLO EXPRESS: Ignorar completamente el puerto del backend
        if not curr_port or not str(curr_port).strip():
            new_port = "1883"  # MQTT sin TLS (hardcoded para v3.0.x)
            updates["port"] = new_port
            final_config["port"] = new_port
            logger.info("Puerto forzado a 1883 (MQTT) para v3.0.x")
        else:
            # Si ya existe en config.ini, respetarlo (permite override manual)
            final_config["port"] = curr_port
            
        # USER - Solo memoria, NUNCA persistir a config.ini
        new_user = rabbit_cfg.get("user", "guest")
        if new_user:
            final_config["user"] = new_user
        else:
            final_config["user"] = "guest"
            
        # PASSWORD - Solo memoria, NUNCA persistir a config.ini
        new_pwd = rabbit_cfg.get("password", "guest")
        if new_pwd:
            final_config["password"] = new_pwd
        else:
            final_config["password"] = "guest"
            
        # VHOST (mantenido por compatibilidad, pero no se usa en MQTT)
        if not curr_vhost or not str(curr_vhost).strip():
            new_vhost = rabbit_cfg.get("vhost", "/")
            if new_vhost:
                updates["vhost"] = new_vhost
                final_config["vhost"] = new_vhost
            else:
                final_config["vhost"] = "/"
        else:
            final_config["vhost"] = curr_vhost
            
        # QUEUE
        if not curr_queue or not str(curr_queue).strip():
            new_queue = rabbit_cfg.get("queue", "")
            if new_queue:
                updates["queue"] = new_queue
                final_config["queue"] = new_queue
            else:
                final_config["queue"] = ""
        else:
            final_config["queue"] = curr_queue
        
        # Log de configuración final (compacto)
        logger.debug(f"MQTT: {final_config['host']}:{final_config['port']}")
        
        # SOLO escribir en config.ini si había campos vacíos que rellenamos
        if updates:
            self.config.set("RabbitMq", updates)
            logger.warning(f"Config rellenada desde SocketIO: {list(updates.keys())}")
            
        # Hacer lo mismo con Paxaprinter
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

        # Guardar credenciales sensibles SOLO en memoria
        vhost = final_config.get('vhost', '/')
        self._update_active_credentials(
            final_config['host'],
            final_config['port'],
            final_config['user'],
            final_config['password'],
            vhost
        )
        
        # Reinicia hilo con la configuración actual
        if self._thread and self._thread.is_alive():
            self.stop(timeout=5)
        self.start(message_queue)