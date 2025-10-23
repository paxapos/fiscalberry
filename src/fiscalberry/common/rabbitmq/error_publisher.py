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
                    logger.info(f"ErrorPublisher configurado para tenant: {self.tenant}")
                else:
                    logger.warning("Tenant no configurado en sección Paxaprinter")
            else:
                logger.warning("Sección Paxaprinter no encontrada - ErrorPublisher deshabilitado")
        except Exception as e:
            logger.error(f"Error configurando tenant info: {e}")
            
    def _get_rabbitmq_config(self) -> Dict[str, Any]:
        """Obtiene la configuración de RabbitMQ."""
        try:
            # Primero intentar obtener credenciales del RabbitMQ Consumer activo
            try:
                from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler
                process_handler = RabbitMQProcessHandler()
                active_creds = process_handler.get_active_rabbitmq_credentials()
                
                if active_creds:
                    logger.info("Usando credenciales activas del RabbitMQ Consumer")
                    return active_creds
            except Exception as e:
                logger.debug(f"No se pudieron obtener credenciales activas: {e}")
            
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
            logger.error(f"Error obteniendo configuración RabbitMQ: {e}")
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
                return True
                
            if not self.tenant or not self.error_queue_name:
                logger.warning("Tenant no configurado - no se puede conectar ErrorPublisher")
                return False
                
            try:
                config = self._get_rabbitmq_config()
                
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
                
                # Declarar exchange para errores
                error_exchange = "fiscalberry_errors"
                self.channel.exchange_declare(
                    exchange=error_exchange,
                    exchange_type='direct',
                    durable=True
                )
                
                # Declarar exchange adicional para el panel de desarrollador (topic para wildcards)
                dev_panel_exchange = "fiscalberry_errors_topic"
                self.channel.exchange_declare(
                    exchange=dev_panel_exchange,
                    exchange_type='topic',
                    durable=True
                )
                
                # Declarar cola específica del tenant
                self.channel.queue_declare(
                    queue=self.error_queue_name,
                    durable=True
                )
                
                # Declarar cola para el panel de desarrollador (captura todos los errores)
                dev_panel_queue = "developer_panel_all_errors"
                self.channel.queue_declare(
                    queue=dev_panel_queue,
                    durable=True
                )
                
                # Enlazar cola del tenant al exchange directo
                self.channel.queue_bind(
                    exchange=error_exchange,
                    queue=self.error_queue_name,
                    routing_key=self.tenant
                )
                
                # Enlazar cola del panel de desarrollador al exchange topic
                self.channel.queue_bind(
                    exchange=dev_panel_exchange,
                    queue=dev_panel_queue,
                    routing_key="*.errors"  # Captura todos los patrones {tenant}.errors
                )
                
                self._is_connected = True
                logger.info(f"ErrorPublisher conectado exitosamente - Cola: {self.error_queue_name}")
                return True
                
            except Exception as e:
                logger.error(f"Error conectando ErrorPublisher: {e}")
                self._is_connected = False
                return False
    
    def disconnect(self):
        """Cierra la conexión con RabbitMQ."""
        with self._lock:
            try:
                if self.connection and not self.connection.is_closed:
                    self.connection.close()
                self._is_connected = False
                logger.info("ErrorPublisher desconectado")
            except Exception as e:
                logger.error(f"Error desconectando ErrorPublisher: {e}")
    
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
            return  # No hay tenant configurado
            
        try:
            # Reconectar si es necesario
            if not self._is_connected:
                if not self.connect():
                    logger.warning("No se pudo conectar ErrorPublisher para publicar error")
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
                    
                    # También publicar al exchange topic para el panel de desarrollador
                    self.channel.basic_publish(
                        exchange="fiscalberry_errors_topic",
                        routing_key=f"{self.tenant}.errors",  # Patrón para wildcard matching
                        body=json.dumps(error_data, ensure_ascii=False),
                        properties=pika.BasicProperties(
                            delivery_mode=2,
                            content_type='application/json',
                            timestamp=int(time.time())
                        )
                    )
                    
                    logger.debug(f"Error publicado a colas {self.error_queue_name} y developer_panel: {error_type}")
                else:
                    logger.warning("Canal RabbitMQ no disponible para publicar error")
                    
        except Exception as e:
            logger.error(f"Error publicando a cola de errores: {e}")
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
        logger.error(f"Error en publish_error: {e}")