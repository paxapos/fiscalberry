import threading
import socket
import os
import time
import logging
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.rabbitmq.consumer import RabbitMQConsumer

logger = logging.getLogger(__name__)


def _override_de_entorno(nombre):
    """
    Escape hatch para cuando la nube manda una config de broker equivocada.

    Va por variable de entorno y NO por config.ini a propósito: el archivo es
    persistente y silencioso (un valor puesto hace años sigue ganando y nadie
    sabe que está ahí), mientras que la variable es deliberada y efímera.
    """
    valor = os.environ.get(nombre, "")
    valor = str(valor).strip()
    return valor or None

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
                # Limpiar consumer activo antes de reset
                if hasattr(cls._instance, '_current_consumer') and cls._instance._current_consumer:
                    try:
                        cls._instance._current_consumer.stop()
                    except Exception:
                        pass
                    cls._instance._current_consumer = None
                # Limpiar stop_event si existe
                if hasattr(cls._instance, '_stop_event'):
                    cls._instance._stop_event.clear()
                # Marcar como no inicializado
                cls._instance._initialized = False
                # Limpiar referencias a threads muertos
                if hasattr(cls._instance, '_thread'):
                    cls._instance._thread = None
                # Limpiar credenciales en memoria
                if hasattr(cls._instance, 'active_credentials'):
                    cls._instance.active_credentials = None

    def __init__(self):
        if self._initialized:
            return
        self._thread = None
        self._stop_event = threading.Event()
        self.config = Configberry()
        # Credenciales activas del MQTT Consumer
        self.active_credentials = None
        # Referencia al consumer activo para poder detenerlo
        self._current_consumer = None
        self._consumer_lock = threading.Lock()
        self._initialized = True

    def get_active_rabbitmq_credentials(self):
        """Retorna las credenciales activas del MQTT Consumer."""
        return self.active_credentials

    def is_running(self):
        """
        Estado REAL del consumer MQTT para la UI/health checks.

        True solo si el hilo del consumer está vivo Y el cliente MQTT está
        efectivamente conectado al broker. Durante backoff/reconexión devuelve
        False (que es lo correcto: no está recibiendo trabajos).
        """
        if not (self._thread and self._thread.is_alive()):
            return False
        consumer = self._current_consumer
        if consumer is not None:
            # _connected refleja el estado real de la conexión MQTT (paho on_connect/on_disconnect)
            return bool(getattr(consumer, "_connected", False))
        # Hilo vivo pero aún sin consumer instanciado: está arrancando.
        return True
    
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
        
        Garantiza limpieza del thread/consumer anterior antes de crear uno nuevo.
        
        NOTA: user y password vienen de active_credentials (memoria),
        no de config.ini, por seguridad.
        """
        # Verificar si hay un thread activo
        if self._thread and self._thread.is_alive():
            logger.warning("MQTT thread ya en ejecución. Esperando que termine...")
            # Dar una oportunidad de terminar limpiamente
            self._stop_event.set()
            self._cleanup_current_consumer()
            self._thread.join(timeout=3)
            if self._thread.is_alive():
                logger.warning("MQTT thread no terminó a tiempo, forzando continuación")
        
        # Limpiar cualquier consumer zombie
        self._cleanup_current_consumer()
        self._thread = None

        # host/port: MEMORIA primero (lo que resolvió configure_and_restart a
        # partir de lo que mandó el servidor). config.ini queda solo como
        # fallback legacy para equipos que todavía no recibieron un start_rabbit.
        host = None
        port = None
        if self.active_credentials:
            host = self.active_credentials.get('host')
            port = self.active_credentials.get('port')
        if not host or not str(host).strip():
            host = self.config.get("RabbitMq", "host")
        if not port or not str(port).strip():
            port = self.config.get("RabbitMq", "port")

        # Credenciales: MEMORIA (active_credentials de SocketIO) PRIMERO, por seguridad.
        # La password del broker nunca se persiste en disco; config.ini es solo override manual.
        user = None
        password = None

        # 1. Primero memoria: credenciales entregadas por la nube vía SocketIO (no tocan disco).
        if self.active_credentials:
            user = self.active_credentials.get('user')
            password = self.active_credentials.get('password')

        # 2. Fallback: config.ini, solo si fue configurado manualmente (instalaciones offline).
        if not user or not str(user).strip():
            user = self.config.get("RabbitMq", "user", fallback=None)
        if not password or not str(password).strip():
            password = self.config.get("RabbitMq", "password", fallback=None)
        
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
        """
        Loop de conexión/reconexión al broker MQTT con backoff exponencial.
        
        Maneja múltiples tipos de errores de red de forma robusta:
        - DNS: socket.gaierror
        - Conexión rechazada: ConnectionRefusedError
        - Timeout: socket.timeout, TimeoutError
        - Red inalcanzable: OSError (varios códigos)
        - Errores MQTT específicos
        """
        retry_count = 0
        max_retries_before_backoff = 3
        base_delay = 5  # segundos
        max_delay = 300  # 5 minutos máximo
        consecutive_errors = 0
        
        while not self._stop_event.is_set():
            try:
                # Verificar conectividad básica antes de intentar conexión MQTT
                if not self._check_network_connectivity(host, int(port)):
                    retry_count += 1
                    consecutive_errors += 1
                    if consecutive_errors <= 3:
                        logger.warning(f"Conectividad de red falló para {host}:{port}")
                    elif consecutive_errors % 10 == 0:
                        # Reducir spam de logs después de muchos errores
                        logger.warning(f"Sin conectividad a {host}:{port} ({consecutive_errors} intentos)")
                    self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
                    continue
                
                # Limpiar consumer anterior si existe (importante para evitar "fantasmas")
                self._cleanup_current_consumer()
                
                consumer = RabbitMQConsumer(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    queue_name=queue_name,
                    message_queue=message_queue
                )
                
                # Guardar referencia al consumer para poder detenerlo desde stop()
                with self._consumer_lock:
                    self._current_consumer = consumer
                
                # Resetear contadores al intentar conexión
                if consecutive_errors > 0:
                    logger.info(f"Conectividad restaurada después de {consecutive_errors} errores")
                consecutive_errors = 0
                
                consumer.start()
                
                # Si llegamos aquí sin excepción, consumer.start() retornó normalmente
                # (desconexión controlada o timeout de reconexión)
                retry_count = 0
                logger.debug("Consumer MQTT terminó, reintentando conexión...")
                
            except socket.gaierror as ex:
                retry_count += 1
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    logger.error(f"Error de resolución DNS para '{host}': {ex}")
                    logger.error("Verificar hostname o usar IP directa")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
                
            except ConnectionRefusedError as ex:
                retry_count += 1
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    logger.error(f"Conexión rechazada por {host}:{port}: {ex}")
                    logger.error("Verificar que el broker MQTT esté ejecutándose y el puerto correcto")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
                
            except (socket.timeout, TimeoutError) as ex:
                retry_count += 1
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    logger.error(f"Timeout conectando a {host}:{port}: {ex}")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
                
            except OSError as ex:
                # Manejar errores de red específicos
                retry_count += 1
                consecutive_errors += 1
                error_codes = {
                    101: "Red inalcanzable",
                    111: "Conexión rechazada",
                    113: "Host inalcanzable",
                    110: "Timeout de conexión",
                }
                error_desc = error_codes.get(ex.errno, f"Error de sistema ({ex.errno})")
                if consecutive_errors <= 3:
                    logger.error(f"{error_desc} para {host}:{port}: {ex}")
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
                
            except Exception as ex:
                retry_count += 1
                consecutive_errors += 1
                logger.error(f"Error inesperado en MQTT Consumer: {ex}", exc_info=True)
                self._handle_retry(retry_count, max_retries_before_backoff, base_delay, max_delay)
                
        logger.info("Salida del bucle de RabbitMQProcessHandler.")
    
    def _cleanup_current_consumer(self):
        """Limpia el consumer actual si existe."""
        with self._consumer_lock:
            if self._current_consumer:
                try:
                    self._current_consumer.stop()
                    logger.debug("Consumer anterior limpiado correctamente")
                except Exception as e:
                    logger.debug(f"Error limpiando consumer anterior: {e}")
                finally:
                    self._current_consumer = None

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

    def stop(self, timeout: float = 5):
        """Detiene el hilo y espera su finalización."""
        if self._thread and self._thread.is_alive():
            logger.debug("Deteniendo MQTT Consumer...")
            self._stop_event.set()
            
            # Detener el consumer activo primero (esto desbloquea el thread)
            self._cleanup_current_consumer()
            
            self._thread.join(timeout)
            if self._thread.is_alive():
                logger.warning("MQTT Consumer no se detuvo a tiempo.")
            else:
                logger.debug("MQTT Consumer detenido correctamente.")
        else:
            logger.debug("No hay hilo de MQTT Consumer en ejecución.")
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
        
        # La infraestructura del broker la decide el SERVIDOR y vive en memoria.
        # `updates` es solo lo que se persiste en config.ini: host/port/vhost ya
        # no entran ahí (ver comentario largo más abajo).
        updates = {}
        final_config = {}

        # HOST: env > servidor > config.ini (fallback legacy)
        env_host = _override_de_entorno("FISCALBERRY_MQTT_HOST")
        srv_host = str(rabbit_cfg.get("host", "") or "").strip()
        if env_host:
            final_config["host"] = env_host
            logger.warning(
                "MQTT host: override local por FISCALBERRY_MQTT_HOST=%s "
                "(el servidor mandó '%s')", env_host, srv_host or "nada")
        elif srv_host:
            final_config["host"] = srv_host
            if str(curr_host).strip() and str(curr_host).strip() != srv_host:
                logger.warning(
                    "MQTT host: se ignora el valor de config.ini ('%s'); "
                    "manda el servidor ('%s')", curr_host, srv_host)
        else:
            final_config["host"] = curr_host or ""
            if str(curr_host).strip():
                logger.warning(
                    "MQTT host: el servidor no mandó host, se cae al de "
                    "config.ini ('%s')", curr_host)

        # PORT: env > servidor (`mqtt_port`) > default local según use_tls.
        #
        # OJO: `rabbit_cfg["port"]` es el puerto AMQP del backend y NO sirve
        # para MQTT: hablarle MQTT a ese puerto da `bad_header` del lado del
        # broker. Por eso el puerto viaja en la clave
        # NUEVA `mqtt_port`, y contra un servidor viejo que no la manda se cae
        # al default local, que es lo que hoy mantiene viva a la flota.
        env_port = _override_de_entorno("FISCALBERRY_MQTT_PORT")
        srv_port = str(rabbit_cfg.get("mqtt_port", "") or "").strip()
        use_tls = str(
            self.config.get("RabbitMq", "use_tls", fallback="false")
        ).strip().lower() in ("true", "1", "yes", "on")
        if env_port:
            final_config["port"] = env_port
            logger.warning(
                "MQTT port: override local por FISCALBERRY_MQTT_PORT=%s "
                "(el servidor mandó '%s')", env_port, srv_port or "nada")
        elif srv_port:
            final_config["port"] = srv_port
        else:
            final_config["port"] = "8883" if use_tls else "1883"
            logger.info(
                "MQTT port: el servidor no mandó 'mqtt_port', se usa el default "
                "local %s (use_tls=%s)", final_config["port"], use_tls)

        if str(curr_port).strip() and str(curr_port).strip() != final_config["port"]:
            logger.warning(
                "MQTT port: config.ini trae '%s' y ya no se usa (se conecta a "
                "'%s'). Para forzarlo, exportá FISCALBERRY_MQTT_PORT.",
                curr_port, final_config["port"])

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
            
        # VHOST (mantenido por compatibilidad, pero no se usa en MQTT).
        # Igual que host/port: lo manda el servidor y no se persiste.
        srv_vhost = str(rabbit_cfg.get("vhost", "") or "").strip()
        final_config["vhost"] = srv_vhost or str(curr_vhost or "").strip() or "/"

        # QUEUE: la define el servidor (igual que tenant/alias), así que un
        # cambio allá tiene que aplicarse acá y no quedar clavado al primer valor.
        new_queue = rabbit_cfg.get("queue", "")
        if new_queue and str(new_queue).strip() != str(curr_queue).strip():
            if str(curr_queue).strip():
                logger.warning(
                    "RabbitMq.queue actualizada desde el servidor: '%s' -> '%s'",
                    curr_queue, new_queue)
            updates["queue"] = new_queue
            final_config["queue"] = new_queue
        else:
            final_config["queue"] = curr_queue or new_queue or ""
        
        # Log de configuración final (compacto)
        logger.debug(f"MQTT: {final_config['host']}:{final_config['port']}")
        
        # Lo único de [RabbitMq] que toca disco es `queue`. Host, puerto, vhost,
        # user y password viven en memoria: lo que no está en el archivo no lo
        # puede ver el usuario ni quedar viejo pisando lo que manda la nube.
        if updates:
            self.config.set("RabbitMq", updates)
            logger.info(f"Config actualizada desde SocketIO: {list(updates.keys())}")
            
        # A QUÉ COMERCIO pertenece el dispositivo lo decide el SERVIDOR, no el
        # archivo local: si en la plataforma se reasigna el equipo a otro tenant,
        # acá tiene que reflejarse. Antes estos campos solo se escribían cuando
        # estaban VACÍOS, así que el primer tenant quedaba grabado para siempre y
        # el cambio hecho en la plataforma no llegaba nunca al dispositivo: los
        # errores se seguían publicando con el tenant viejo y la UI mostraba el
        # comercio equivocado.
        #
        # Los campos de infraestructura (host/port/vhost) siguen la misma regla:
        # los decide el servidor. Antes ganaba config.ini "porque un override
        # manual es una decisión legítima de quien instala el equipo", pero en
        # la práctica eso dejó un local sin imprimir semanas con un puerto viejo
        # clavado en el archivo que nadie sabía que estaba ahí. El override sigue
        # existiendo, pero por variable de entorno: deliberado y efímero.
        pax_cfg = data.get('Paxaprinter', {})
        pax_updates = {}

        for clave in ("alias", "tenant", "site_name"):
            nuevo = pax_cfg.get(clave)
            if not nuevo:
                continue
            actual = self.config.get("Paxaprinter", clave, fallback="")
            if str(actual).strip() == str(nuevo).strip():
                continue
            pax_updates[clave] = nuevo
            if str(actual).strip():
                logger.warning(
                    "Paxaprinter.%s actualizado desde el servidor: '%s' -> '%s'",
                    clave, actual, nuevo)

        if pax_updates:
            self.config.set("Paxaprinter", pax_updates)
            logger.info(f"Datos del comercio actualizados: {list(pax_updates.keys())}")

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