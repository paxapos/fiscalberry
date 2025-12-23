"""
Sistema de publicación de errores por tenant en RabbitMQ.

Este módulo maneja la publicación de logs de errores a subcolas específicas
para cada tenant/comercio, permitiendo monitoreo remoto de errores.
"""

import json
import threading
import time
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
import pika
import pika.exceptions

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.Configberry import Configberry

logger = getLogger()


class ErrorPublisher:
    """
    Publicador de errores a subcolas específicas por tenant.
    
    Funcionalidades:
    - Publica errores a subcolas con formato: {tenant}_errors
    - Mantiene una conexión persistente pero resiliente
    - Maneja reconexiones automáticas
    - Formatea los errores con metadata útil
    """
    
    def __init__(self):
        self.config = Configberry()
        self.connection = None
        self.channel = None
        self.tenant = None
        self.error_queue_name = None
        self._lock = threading.Lock()
        self._is_connected = False
        
        # Configurar información del tenant
        self._setup_tenant_info()
        
    def _setup_tenant_info(self):
        """Configura la información del tenant desde la configuración."""
        try:
            if self.config.config.has_section("Paxaprinter"):
                self.tenant = self.config.get("Paxaprinter", "tenant", fallback="")
                if self.tenant:
                    self.error_queue_name = f"{self.tenant}_errors"
                    logger.info("ErrorPublisher initialized - Tenant: %s, Queue: %s", 
                               self.tenant, self.error_queue_name)
                else:
                    logger.warning("ErrorPublisher: Tenant not configured in Paxaprinter section")
            else:
                logger.debug("ErrorPublisher: Paxaprinter section not found - error publishing disabled")
        except Exception as e:
            logger.error("ErrorPublisher: Failed to setup tenant info - %s", e)
            logger.debug(traceback.format_exc())
            
    def _get_rabbitmq_config(self) -> Dict[str, Any]:
        """Obtiene la configuración de RabbitMQ."""
        try:
            # Primero intentar obtener credenciales del RabbitMQ Consumer activo
            try:
                from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler
                process_handler = RabbitMQProcessHandler()
                active_creds = process_handler.get_active_rabbitmq_credentials()
                
                if active_creds:
                    logger.debug("ErrorPublisher: Using active RabbitMQ consumer credentials")
                    return active_creds
            except Exception as e:
                logger.debug("ErrorPublisher: Could not obtain active credentials, using config - %s", e)
            
            # Intentar obtener configuración de Paxaprinter primero
            if self.config.config.has_section("Paxaprinter"):
                return {
                    'host': self.config.get("Paxaprinter", "rabbitmq_host", fallback="localhost"),
                    'port': int(self.config.get("Paxaprinter", "rabbitmq_port", fallback="5672")),
                    'user': self.config.get("Paxaprinter", "rabbitmq_user", fallback="guest"),
                    'password': self.config.get("Paxaprinter", "rabbitmq_password", fallback="guest"),
                    'vhost': self.config.get("Paxaprinter", "rabbitmq_vhost", fallback="/")
                }
            
            # Fallback a configuración RabbitMq
            if self.config.config.has_section("RabbitMq"):
                return {
                    'host': self.config.get("RabbitMq", "host", fallback="localhost"),
                    'port': int(self.config.get("RabbitMq", "port", fallback="5672")),
                    'user': self.config.get("RabbitMq", "user", fallback="guest"),
                    'password': self.config.get("RabbitMq", "password", fallback="guest"),
                    'vhost': self.config.get("RabbitMq", "vhost", fallback="/")
                }
                
            return {
                'host': 'localhost',
                'port': 5672,
                'user': 'guest',
                'password': 'guest',
                'vhost': '/'
            }
            
        except Exception as e:
            logger.error("ErrorPublisher: Failed to get RabbitMQ config - %s", e)
            logger.debug(traceback.format_exc())
            return {
                'host': 'localhost',
                'port': 5672,
                'user': 'guest',
                'password': 'guest',
                'vhost': '/'
            }
    
    def connect(self) -> bool:
        """
        Establece conexión con RabbitMQ y configura el exchange y cola de errores.
        
        Returns:
            bool: True si la conexión fue exitosa, False en caso contrario
        """
        with self._lock:
            if self._is_connected and self.connection and not self.connection.is_closed:
                logger.debug("ErrorPublisher: Already connected")
                return True
                
            if not self.tenant or not self.error_queue_name:
                logger.warning("ErrorPublisher: Cannot connect - tenant not configured")
                return False
                
            try:
                config = self._get_rabbitmq_config()
                
                logger.debug("ErrorPublisher: Connecting to RabbitMQ - Host: %s:%s, VHost: %s, User: %s",
                           config['host'], config['port'], config['vhost'], config['user'])
                
                credentials = pika.PlainCredentials(config['user'], config['password'])
                parameters = pika.ConnectionParameters(
                    host=config['host'],
                    port=config['port'],
                    virtual_host=config['vhost'],
                    credentials=credentials,
                    socket_timeout=10,
                    connection_attempts=1,
                    retry_delay=1
                )
                
                # Establecer conexión
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()
                
                logger.debug("ErrorPublisher: RabbitMQ connection established")
                
                # Declarar exchange para errores
                error_exchange = "fiscalberry_errors"
                self.channel.exchange_declare(
                    exchange=error_exchange,
                    exchange_type='direct',
                    durable=True
                )
                
                logger.debug("ErrorPublisher: Exchange declared - %s (direct)", error_exchange)
                
                # Declarar cola específica del tenant
                self.channel.queue_declare(
                    queue=self.error_queue_name,
                    durable=True
                )
                
                logger.debug("ErrorPublisher: Queue declared - %s (tenant)", self.error_queue_name)
                
                # Enlazar cola del tenant al exchange directo
                self.channel.queue_bind(
                    exchange=error_exchange,
                    queue=self.error_queue_name,
                    routing_key=self.tenant
                )
                
                self._is_connected = True
                logger.info("ErrorPublisher connected - Tenant: %s, Queue: %s, Exchange: %s",
                           self.tenant, self.error_queue_name, error_exchange)
                return True
                
            except Exception as e:
                logger.error("ErrorPublisher: Connection failed - %s", e)
                logger.debug(traceback.format_exc())
                self._is_connected = False
                return False
    
    def disconnect(self):
        """Cierra la conexión con RabbitMQ."""
        with self._lock:
            try:
                if self.connection and not self.connection.is_closed:
                    self.connection.close()
                self._is_connected = False
                logger.debug("ErrorPublisher disconnected")
            except Exception as e:
                logger.error("ErrorPublisher: Disconnect failed - %s", e)
                logger.debug(traceback.format_exc())
    
    def publish_error(self, error_type: str, error_message: str, 
                     context: Optional[Dict[str, Any]] = None, 
                     exception: Optional[Exception] = None):
        """
        Publica un error a la subcola del tenant.
        
        Args:
            error_type: Tipo de error (ej: "PRINTER_ERROR", "JSON_PARSE_ERROR")
            error_message: Mensaje descriptivo del error
            context: Contexto adicional (datos del comando, configuración, etc.)
            exception: Excepción original si está disponible
        """
        if not self.tenant:
            logger.debug("ErrorPublisher: No tenant configured, skipping error publication")
            return  # No hay tenant configurado
            
        try:
            # Reconectar si es necesario
            if not self._is_connected:
                logger.debug("ErrorPublisher: Not connected, attempting connection...")
                if not self.connect():
                    logger.warning("ErrorPublisher: Failed to connect - error not published")
                    return
            
            # Preparar payload del error
            error_data = {
                'timestamp': datetime.now().isoformat(),
                'tenant': self.tenant,
                'error_type': error_type,
                'message': error_message,
                'device_uuid': self.config.get("SERVIDOR", "uuid", fallback="unknown"),
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
            
            # Publicar al exchange directo (para el tenant específico)
            with self._lock:
                if self.channel and not self.channel.is_closed:
                    # Publicar al exchange directo del tenant
                    self.channel.basic_publish(
                        exchange="fiscalberry_errors",
                        routing_key=self.tenant,
                        body=json.dumps(error_data, ensure_ascii=False),
                        properties=pika.BasicProperties(
                            delivery_mode=2,  # Hacer el mensaje persistente
                            content_type='application/json',
                            timestamp=int(time.time())
                        )
                    )
                    
                    logger.info("Error published to RabbitMQ - Type: %s, Tenant: %s, Queue: %s",
                               error_type, self.tenant, self.error_queue_name)
                else:
                    logger.warning("ErrorPublisher: RabbitMQ channel unavailable - error not published")
                    
        except Exception as e:
            logger.error("ErrorPublisher: Failed to publish error - %s", e)
            logger.debug(traceback.format_exc())
            # Marcar como desconectado para forzar reconexión
            self._is_connected = False


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
    Función de conveniencia para publicar errores.
    
    Args:
        error_type: Tipo de error (ej: "PRINTER_ERROR", "JSON_PARSE_ERROR")
        error_message: Mensaje descriptivo del error
        context: Contexto adicional (datos del comando, configuración, etc.)
        exception: Excepción original si está disponible
    """
    try:
        publisher = get_error_publisher()
        publisher.publish_error(error_type, error_message, context, exception)
    except Exception as e:
        logger.error("publish_error: Critical failure - %s", e)
        logger.debug(traceback.format_exc())