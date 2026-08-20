"""
Sistema de publicación de errores por tenant usando MQTT.

Este módulo maneja la publicación de logs de errores a topics específicos
para cada tenant/comercio, permitiendo monitoreo remoto de errores.
"""

import json
import queue
import threading
import time
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
import paho.mqtt.client as mqtt

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.rabbitmq import mqtt_compat

logger = getLogger()


class ErrorPublisher:
    """
    Publicador de errores a topics MQTT específicos por tenant.
    
    Funcionalidades:
    - Publica errores a topics con formato: fiscalberry/errors/{tenant}/{uuid}
    - Mantiene una conexión persistente pero resiliente
    - Maneja reconexiones automáticas
    - Formatea los errores con metadata útil
    """
    
    MQTT_PORT_DEFAULT = 1883
    
    def __init__(self):
        self.config = Configberry()
        self.client = None
        self.tenant = None
        self.uuid = None
        self.error_topic = None
        self._lock = threading.Lock()
        self._connected = False
        
        # Configurar información del tenant
        self._setup_tenant_info()
        
    def _setup_tenant_info(self):
        """Configura la información del tenant desde la configuración."""
        try:
            # El uuid identifica la cola/dispositivo (correlaciona con el panel admin).
            self.uuid = self.config.get("SERVIDOR", "uuid", fallback="unknown")
            if self.config.config.has_section("Paxaprinter"):
                self.tenant = self.config.get("Paxaprinter", "tenant", fallback="")
                if self.tenant:
                    # Topic con tenant + uuid: permite al panel rutear por routing key
                    # fiscalberry.errors.{tenant}.{uuid} sin depender del payload.
                    self.error_topic = f"fiscalberry/errors/{self.tenant}/{self.uuid}"
                    logger.debug("ErrorPublisher initialized - Tenant: %s, Topic: %s", 
                               self.tenant, self.error_topic)
            else:
                logger.debug("ErrorPublisher: Paxaprinter section not found - error publishing disabled")
        except Exception as e:
            logger.error("ErrorPublisher: Failed to setup tenant info - %s", e)
            logger.debug(traceback.format_exc())
            
    def _get_mqtt_config(self) -> Dict[str, Any]:
        """Obtiene la configuración de MQTT."""
        try:
            # Primero intentar obtener credenciales del RabbitMQ Consumer activo
            try:
                from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler
                process_handler = RabbitMQProcessHandler()
                active_creds = process_handler.get_active_rabbitmq_credentials()
                
                if active_creds:
                    logger.debug("ErrorPublisher: Using active MQTT consumer credentials")
                    return {
                        'host': active_creds.get('host', 'localhost'),
                        'port': int(active_creds.get('port', self.MQTT_PORT_DEFAULT)),
                        'user': active_creds.get('user', 'guest'),
                        'password': active_creds.get('password', 'guest')
                    }
            except Exception as e:
                logger.debug("ErrorPublisher: Could not obtain active credentials, using config - %s", e)
            
            # Intentar obtener configuración de Paxaprinter primero
            if self.config.config.has_section("Paxaprinter"):
                return {
                    'host': self.config.get("Paxaprinter", "rabbitmq_host", fallback="localhost"),
                    'port': int(self.config.get("Paxaprinter", "rabbitmq_port", fallback=str(self.MQTT_PORT_DEFAULT))),
                    'user': self.config.get("Paxaprinter", "rabbitmq_user", fallback="guest"),
                    'password': self.config.get("Paxaprinter", "rabbitmq_password", fallback="guest")
                }
            
            # Fallback a configuración RabbitMq
            if self.config.config.has_section("RabbitMq"):
                return {
                    'host': self.config.get("RabbitMq", "host", fallback="localhost"),
                    'port': int(self.config.get("RabbitMq", "port", fallback=str(self.MQTT_PORT_DEFAULT))),
                    'user': self.config.get("RabbitMq", "user", fallback="guest"),
                    'password': self.config.get("RabbitMq", "password", fallback="guest")
                }
                
            return {
                'host': 'localhost',
                'port': self.MQTT_PORT_DEFAULT,
                'user': 'guest',
                'password': 'guest'
            }
            
        except Exception as e:
            logger.error("ErrorPublisher: Failed to get MQTT config - %s", e)
            logger.debug(traceback.format_exc())
            return {
                'host': 'localhost',
                'port': self.MQTT_PORT_DEFAULT,
                'user': 'guest',
                'password': 'guest'
            }
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback cuando se conecta al broker MQTT."""
        if mqtt_compat.rc_is_success(rc):
            self._connected = True
            logger.debug("ErrorPublisher: MQTT conectado")
        else:
            self._connected = False
            logger.error("ErrorPublisher: Error de conexión MQTT (rc=%s)", rc)
            
    def _on_disconnect(self, client, userdata, rc):
        """Callback cuando se desconecta del broker MQTT."""
        self._connected = False
        if rc != 0:
            logger.debug("ErrorPublisher: Desconexión inesperada (rc=%s)", rc)
            
    def _on_publish(self, client, userdata, mid):
        """Callback cuando se publica un mensaje."""
        logger.debug("ErrorPublisher: Mensaje publicado (mid=%s)", mid)
    
    def connect(self) -> bool:
        """
        Establece conexión con el broker MQTT.
        
        Returns:
            bool: True si la conexión fue exitosa, False en caso contrario
        """
        with self._lock:
            if self._connected and self.client:
                logger.debug("ErrorPublisher: Already connected")
                return True
                
            if not self.tenant or not self.error_topic:
                return False
                
            try:
                config = self._get_mqtt_config()
                
                logger.debug("ErrorPublisher: Connecting to MQTT - Host: %s:%s, User: %s",
                           config['host'], config['port'], config['user'])
                
                # Crear cliente MQTT (compatible paho 1.x/2.x)
                self.client = mqtt_compat.make_client(
                    client_id=f"fiscalberry-errors-{self.tenant}-{self.uuid}",
                    clean_session=True,  # Para errores no necesitamos sesión persistente
                    protocol=mqtt.MQTTv311,
                )
                
                # Configurar credenciales
                self.client.username_pw_set(config['user'], config['password'])

                # TLS opt-in (misma config local que el consumer).
                try:
                    tls_cfg = mqtt_compat.read_mqtt_tls_config(self.config)
                    mqtt_compat.apply_tls(self.client, tls_cfg)
                except Exception as tls_err:
                    logger.debug("ErrorPublisher: no se pudo aplicar TLS: %s", tls_err)
                
                # Configurar callbacks
                self.client.on_connect = self._on_connect
                self.client.on_disconnect = self._on_disconnect
                self.client.on_publish = self._on_publish
                
                # Conectar
                self.client.connect(config['host'], config['port'], keepalive=60)
                
                # Iniciar loop en segundo plano
                self.client.loop_start()
                
                # Esperar conexión con timeout
                timeout = 5
                start = time.time()
                while not self._connected and (time.time() - start) < timeout:
                    time.sleep(0.1)
                
                if self._connected:
                    logger.debug("ErrorPublisher connected - Tenant: %s, Topic: %s",
                               self.tenant, self.error_topic)
                    return True
                else:
                    logger.error("ErrorPublisher: Connection timeout")
                    return False
                
            except Exception as e:
                logger.error("ErrorPublisher: Connection failed - %s", e)
                logger.debug(traceback.format_exc())
                self._connected = False
                return False
    
    def disconnect(self):
        """Cierra la conexión con el broker MQTT."""
        with self._lock:
            try:
                if self.client:
                    self.client.loop_stop()
                    self.client.disconnect()
                self._connected = False
                logger.debug("ErrorPublisher disconnected")
            except Exception as e:
                logger.error("ErrorPublisher: Disconnect failed - %s", e)
                logger.debug(traceback.format_exc())
    
    def publish_error(self, error_type: str, error_message: str, 
                     context: Optional[Dict[str, Any]] = None, 
                     exception: Optional[Exception] = None):
        """
        Publica un error al topic MQTT del tenant.
        
        Args:
            error_type: Tipo de error (ej: "PRINTER_ERROR", "JSON_PARSE_ERROR")
            error_message: Mensaje descriptivo del error
            context: Contexto adicional (datos del comando, configuración, etc.)
            exception: Excepción original si está disponible
        """
        if not self.tenant:
            logger.debug("ErrorPublisher: No tenant configured, skipping error publication")
            return
            
        try:
            # Reconectar si es necesario
            if not self._connected:
                logger.debug("ErrorPublisher: Not connected, attempting connection...")
                if not self.connect():
                    return
            
            # Preparar payload del error
            error_data = {
                'timestamp': datetime.now().isoformat(),
                'tenant': self.tenant,
                'error_type': error_type,
                'message': error_message,
                'device_uuid': self.uuid or self.config.get("SERVIDOR", "uuid", fallback="unknown"),
                'context': context or {}
            }
            
            # Agregar información de la excepción si está disponible
            if exception:
                error_data['exception'] = {
                    'type': type(exception).__name__,
                    'args': str(exception.args),
                    'traceback': traceback.format_exc()
                }
                logger.debug("ErrorPublisher: Exception details included in error payload")
            
            # Log del error que se va a publicar
            logger.error("[%s] %s (Tenant: %s)", error_type, error_message, self.tenant)
            logger.debug("ErrorPublisher: Publishing error - Type: %s, Context keys: %s",
                        error_type, list(context.keys()) if context else [])
            
            # Publicar al topic MQTT con QoS 1 para garantizar entrega
            with self._lock:
                if self.client and self._connected:
                    result = self.client.publish(
                        self.error_topic,
                        json.dumps(error_data, ensure_ascii=False),
                        qos=1  # At least once delivery
                    )
                    
                    logger.debug("Error published to MQTT - Type: %s, Tenant: %s, Topic: %s, mid: %s",
                               error_type, self.tenant, self.error_topic, result.mid)
                    
        except Exception as e:
            logger.error("ErrorPublisher: Failed to publish error - %s", e)
            logger.debug(traceback.format_exc())
            # Marcar como desconectado para forzar reconexión
            self._connected = False


# Singleton global para el publisher de errores
_error_publisher_instance = None
_error_publisher_lock = threading.Lock()


def get_error_publisher() -> ErrorPublisher:
    """
    Obtiene la instancia singleton del ErrorPublisher.
    
    Returns:
        ErrorPublisher: Instancia del publicador de errores
    """
    global _error_publisher_instance
    
    with _error_publisher_lock:
        if _error_publisher_instance is None:
            _error_publisher_instance = ErrorPublisher()
        return _error_publisher_instance


def publish_error(error_type: str, error_message: str, 
                 context: Optional[Dict[str, Any]] = None, 
                 exception: Optional[Exception] = None):
    """
    Publica un error de forma NO BLOQUEANTE (Fase 6).

    Encola el error y retorna de inmediato: la publicación real la hace un worker
    de fondo. Nunca bloquea el hilo de impresión ni lanza excepciones aunque el
    broker esté caído. Sanitiza el contexto (no expone credenciales) y aplica un
    rate-limit por tipo de error para no spamear.
    """
    try:
        _error_dispatcher.submit({
            "error_type": error_type,
            "error_message": error_message,
            "context": _sanitize_context(context) if context else None,
            "exception": exception,
        })
    except Exception:
        # Reportar un error NUNCA debe romper el flujo principal (impresión).
        pass


# ---------------------------------------------------------------------------
# Despachador no bloqueante (Fase 6)
# ---------------------------------------------------------------------------
# Claves cuyo valor se enmascara antes de publicar (no exponer secretos).
_SENSITIVE_KEYS = {
    "password", "passwd", "pwd", "secret", "token", "authorization", "auth",
    "apikey", "api_key", "credential", "credentials", "rabbitmq_password",
}


def _sanitize_context(obj, _depth=0):
    """Enmascara valores sensibles en el contexto antes de publicarlo."""
    if _depth > 6:
        return "..."
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in _SENSITIVE_KEYS:
                out[k] = "***"
            else:
                out[k] = _sanitize_context(v, _depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_sanitize_context(v, _depth + 1) for v in obj]
    return obj


class _ErrorDispatcher:
    """Cola acotada + worker de fondo para publicar errores sin bloquear.

    - No arranca ningún thread hasta el primer error (import-safe).
    - Si la cola se llena, descarta el más viejo (best-effort), nunca bloquea.
    - Rate-limit por error_type para evitar tormentas de mensajes.
    """

    MAXSIZE = 100
    MIN_INTERVAL = 5.0  # segundos entre errores del mismo tipo

    def __init__(self):
        self._q = queue.Queue(maxsize=self.MAXSIZE)
        self._last_sent = {}
        self._lock = threading.Lock()
        self._started = False

    def _ensure_worker(self):
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            threading.Thread(
                target=self._run, name="error-publisher", daemon=True).start()
            self._started = True

    def submit(self, item):
        error_type = item.get("error_type", "")
        now = time.time()
        with self._lock:
            last = self._last_sent.get(error_type, 0.0)
            if now - last < self.MIN_INTERVAL:
                return  # Descartar repetido reciente (rate-limit).
            self._last_sent[error_type] = now
        self._ensure_worker()
        try:
            self._q.put_nowait(item)
        except queue.Full:
            # Cola llena: soltar el más viejo y encolar el nuevo (best-effort).
            try:
                self._q.get_nowait()
                self._q.put_nowait(item)
            except Exception:
                pass

    def _run(self):
        while True:
            item = self._q.get()
            try:
                get_error_publisher().publish_error(
                    error_type=item.get("error_type", "UNKNOWN"),
                    error_message=item.get("error_message", ""),
                    context=item.get("context"),
                    exception=item.get("exception"),
                )
            except Exception as e:
                logger.debug("ErrorPublisher dispatcher: fallo publicando (ignorado): %s", e)


_error_dispatcher = _ErrorDispatcher()