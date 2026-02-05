"""
MQTT Consumer para Fiscalberry.

Este módulo maneja la conexión MQTT con RabbitMQ (plugin MQTT habilitado)
para recibir comandos de impresión.
"""

import json
import time
import traceback
import paho.mqtt.client as mqtt

from fiscalberry.common.ComandosHandler import ComandosHandler, TraductorException
from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.rabbitmq.error_publisher import publish_error
from typing import Optional
import queue


class RabbitMQConsumer:
    """
    Consumidor MQTT para recibir comandos de impresión desde RabbitMQ.
    
    Usa el plugin MQTT de RabbitMQ en lugar de AMQP (pika).
    Características:
    - clean_session=False: Sesión persistente para no perder mensajes
    - QoS 1: ACK automático cuando on_message termina sin errores
    - Reconexión automática con backoff exponencial
    - Keepalive agresivo (30s) para detectar conexiones muertas
    """
    
    MQTT_PORT_DEFAULT = 1883
    KEEPALIVE_SECONDS = 30  # Reducido de 60s para detectar conexiones muertas más rápido
    SOCKET_TIMEOUT_SECONDS = 10  # Timeout para operaciones de socket
    MAX_BINDING_RETRIES = 3  # Intentos máximos para crear binding
    
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        queue_name: str,
        message_queue: Optional[queue.Queue] = None,
        vhost: str = "/"
    ) -> None:
        self.logger = getLogger("MQTT.Consumer")
        
        # El topic es el UUID de la impresora
        self.topic = queue_name
        
        self.logger.debug(f"MQTT Consumer: {host}:{port} topic={self.topic}")
        
        self.host = host
        self.port = int(port) if port else self.MQTT_PORT_DEFAULT
        self.user = user
        self.password = password
        self.message_queue = message_queue
        
        
        # Cliente MQTT
        self.client = None
        self._connected = False
        self._subscribed = False
        self._stop_requested = False
        self._binding_created = False
        
        # Handler de comandos reutilizable (evita crear instancia por mensaje)
        self._comandos_handler = None
        
        # Configuración AMQP para crear binding
        self.AMQP_PORT = 5672
        self.EXCHANGE_NAME = 'paxaprinter'
        
    def _create_queue_binding(self):
        """
        Crea el binding entre el exchange AMQP 'paxaprinter' y la cola MQTT.
        
        IMPORTANTE: Este método se ejecuta DESPUÉS de que el cliente MQTT se conecta,
        porque la cola MQTT se crea automáticamente cuando el cliente se conecta con
        clean_session=False.
        
        El orden correcto es:
        1. Cliente MQTT se conecta → RabbitMQ crea la cola automáticamente
        2. Este método crea el binding exchange → cola
        
        Si este binding falla, los mensajes del backend NO llegarán a la cola.
        Se reintenta hasta MAX_BINDING_RETRIES veces con backoff.
        
        Returns:
            bool: True si el binding se creó exitosamente, False si falló
        """
        for attempt in range(1, self.MAX_BINDING_RETRIES + 1):
            try:
                import pika
                
                # Nombre de la cola que MQTT ya creó
                mqtt_queue_name = f"mqtt-subscription-fiscalberry-{self.topic}qos1"
                
                self.logger.debug("Creando binding AMQP (intento %d/%d): exchange '%s' → queue '%s'", 
                               attempt, self.MAX_BINDING_RETRIES, self.EXCHANGE_NAME, mqtt_queue_name)
                
                # Conectar via AMQP temporalmente solo para crear el binding
                credentials = pika.PlainCredentials(self.user, self.password)
                connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=self.host,
                        port=self.AMQP_PORT,
                        credentials=credentials,
                        socket_timeout=self.SOCKET_TIMEOUT_SECONDS,
                        connection_attempts=2,
                        retry_delay=1
                    )
                )
                channel = connection.channel()
                
                channel.queue_bind(
                    exchange=self.EXCHANGE_NAME,
                    queue=mqtt_queue_name,
                    routing_key=self.topic
                )
                
                connection.close()
                
                self.logger.debug("✓ Binding creado exitosamente: %s → %s", 
                               self.EXCHANGE_NAME, mqtt_queue_name)
                self._binding_created = True
                return True
                
            except ImportError:
                self.logger.error("ERROR FATAL: pika no está instalado. No se puede crear el binding AMQP.")
                return False
                
            except Exception as e:
                self.logger.warning("Error creando binding (intento %d/%d): %s", 
                                  attempt, self.MAX_BINDING_RETRIES, e)
                if attempt < self.MAX_BINDING_RETRIES:
                    # Backoff entre intentos
                    time.sleep(2 ** attempt)
                else:
                    self.logger.error("ERROR: No se pudo crear binding después de %d intentos.", 
                                    self.MAX_BINDING_RETRIES)
                    self.logger.error("Los mensajes del backend NO llegarán a esta impresora.")
                    return False
        
        return False
    def _on_connect(self, client, userdata, flags, rc):
        """Callback cuando se conecta al broker MQTT."""
        if rc == 0:
            self.logger.debug("MQTT conectado exitosamente")
            self._connected = True
            # Suscribirse al topic con QoS 1 para ACK automático
            client.subscribe(self.topic, qos=1)
            self.logger.debug(f"Suscrito a topic: {self.topic}")
        else:
            error_messages = {
                1: "Protocolo incorrecto",
                2: "Identificador de cliente inválido",
                3: "Servidor no disponible",
                4: "Usuario/contraseña incorrectos",
                5: "No autorizado"
            }
            error_msg = error_messages.get(rc, f"Error desconocido (código {rc})")
            self.logger.error(f"Error de conexión MQTT: {error_msg}")
            self._connected = False
            
    def _on_disconnect(self, client, userdata, rc):
        """Callback cuando se desconecta del broker MQTT."""
        self._connected = False
        self._subscribed = False
        # IMPORTANTE: Resetear binding para que se recree en la próxima conexión
        self._binding_created = False
        if rc != 0:
            self.logger.warning(f"Desconexión inesperada de MQTT (rc={rc}). Se intentará reconectar automáticamente.")
        else:
            self.logger.debug("MQTT desconectado correctamente")
            
    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """
        Callback cuando la suscripción es confirmada.
        
        En este punto, la cola MQTT ya fue creada por RabbitMQ.
        Ahora creamos el binding exchange → queue para que los mensajes lleguen.
        """
        self._subscribed = True
        self.logger.debug(f"Suscripción confirmada (QoS: {granted_qos})")
        
        # Ahora que la cola MQTT existe, crear el binding
        if not self._binding_created:
            success = self._create_queue_binding()
            if not success:
                self.logger.error("ATENCIÓN: Fiscalberry está conectado pero NO recibirá mensajes.")
                self.logger.error("Solución: Crear el binding manualmente en RabbitMQ o verificar permisos.")
        
    def _on_message(self, client, userdata, msg):
        """
        Callback cuando llega un mensaje MQTT.
        
        Con QoS 1, el ACK se envía automáticamente cuando esta función
        termina sin errores. Si hay una excepción, el mensaje quedará
        en la cola para reintentar.
        """
        start_time = time.time()
        body_str = None
        
        try:
            # Decodificar payload
            if isinstance(msg.payload, bytes):
                body_str = msg.payload.decode('utf-8')
            else:
                body_str = msg.payload
                
            # Parse JSON
            try:
                json_data = json.loads(body_str)
            except json.JSONDecodeError as json_err:
                self.logger.warning("Mensaje no es JSON válido: %s", json_err)
                # Publicar error pero continuar (algunos comandos pueden ser texto plano)
                publish_error(
                    error_type="JSON_PARSE_WARNING",
                    error_message=f"Mensaje no es JSON válido: {str(json_err)}",
                    context={
                        "raw_body": body_str[:200] if body_str else "",
                        "topic": self.topic
                    }
                )
                json_data = body_str
                
            # Procesar comando (reutilizar handler para mejor rendimiento)
            if self._comandos_handler is None:
                self._comandos_handler = ComandosHandler()
            result = self._comandos_handler.send_command(json_data)
            
            processing_time = time.time() - start_time
            
            # Verificar errores en el resultado
            if "err" in result:
                error_msg = result['err']
                self.logger.error("Error ejecutando comando: %s", error_msg)
                
                # Publicar error
                publish_error(
                    error_type="COMMAND_EXECUTION_ERROR",
                    error_message=error_msg,
                    context={
                        "command": json_data,
                        "result": result,
                        "topic": self.topic
                    }
                )
                # Con QoS 1, el mensaje se marca como procesado aunque haya error
                # porque la lógica de negocio lo procesó (no queremos reintento infinito)
                return
                
            # Log solo para trabajos lentos
            if processing_time > 1.0:
                self.logger.warning(f"Mensaje procesado lentamente: {processing_time:.2f}s")
                
        except TraductorException as e:
            self.logger.error("Error de traducción: %s", e)
            publish_error(
                error_type="TRANSLATOR_ERROR",
                error_message=str(e),
                context={
                    "command": body_str[:500] if body_str else "",
                    "topic": self.topic
                },
                exception=e
            )
            
        except Exception as e:
            self.logger.error("Error procesando mensaje: %s", e)
            publish_error(
                error_type="PROCESSING_ERROR",
                error_message=f"Error procesando mensaje: {str(e)}",
                context={
                    "raw_body": body_str[:500] if body_str else "",
                    "topic": self.topic
                },
                exception=e
            )
    
    def connect(self):
        """Conecta al broker MQTT con configuración robusta para redes inestables."""
        try:
            # Crear cliente MQTT con sesión persistente
            self.client = mqtt.Client(
                client_id=f"fiscalberry-{self.topic}",
                clean_session=False,  # CRÍTICO: Sesión persistente
                protocol=mqtt.MQTTv311
            )
            
            # Configurar credenciales
            self.client.username_pw_set(self.user, self.password)
            
            # Habilitar reconexión automática con backoff (1s min, 120s max)
            self.client.reconnect_delay_set(min_delay=1, max_delay=120)
            
            # Configurar callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_subscribe = self._on_subscribe
            self.client.on_message = self._on_message
            
            # Conectar via MQTT con keepalive reducido (30s) para detectar conexiones muertas rápido
            # Nota: paho-mqtt maneja timeouts internamente, el keepalive sirve para detectar
            # conexiones zombies donde el broker no responde
            self.client.connect(self.host, self.port, keepalive=self.KEEPALIVE_SECONDS)
            
            self.logger.debug(f"Conectando a MQTT: {self.host}:{self.port} (keepalive={self.KEEPALIVE_SECONDS}s)")
            
        except Exception as e:
            self.logger.error(f"Error conectando a MQTT: {e}")
            raise
            
    def start(self):
        """
        Inicia el loop de consumo de mensajes MQTT.
        
        Usa loop_start() en lugar de loop_forever() para poder interrumpir
        desde otro thread mediante stop().
        """
        self._stop_requested = False
        self.connect()
        
        self.logger.info(f"Esperando mensajes en topic: {self.topic}")
        
        # Contador para detectar desconexión prolongada
        disconnected_seconds = 0
        MAX_DISCONNECT_SECONDS = 300  # 5 minutos máximo esperando reconexión
        
        try:
            # Usar loop_start() (no bloqueante) + polling para poder interrumpir
            self.client.loop_start()
            
            # Polling loop - verifica periódicamente si debemos detenernos
            while not self._stop_requested:
                if not self._connected:
                    disconnected_seconds += 1
                    if disconnected_seconds >= MAX_DISCONNECT_SECONDS:
                        self.logger.error(f"Sin conexión MQTT por {MAX_DISCONNECT_SECONDS}s. Saliendo para permitir reconexión completa.")
                        break  # Salir para que process_handler reintente con nuevo consumer
                    if disconnected_seconds % 30 == 0:  # Log cada 30s
                        self.logger.warning(f"Esperando reconexión MQTT... ({disconnected_seconds}s)")
                    time.sleep(1)
                    continue
                else:
                    disconnected_seconds = 0  # Reset contador si estamos conectados
                time.sleep(0.5)  # Check cada 500ms
                
        except Exception as e:
            self.logger.error(f"Error en consumer MQTT: {e}")
            self.logger.error(traceback.format_exc())
            raise
        finally:
            # Asegurar limpieza al salir
            self._cleanup()
            
    def _cleanup(self):
        """Limpieza interna de la conexión MQTT. Garantiza desconexión limpia."""
        if self.client:
            try:
                # Primero detener el loop de red
                self.client.loop_stop()
                
                # Luego desconectar limpiamente
                try:
                    self.client.disconnect()
                except Exception:
                    pass  # Ignorar si ya está desconectado
                
                # Limpiar referencia
                self.client = None
                self._connected = False
                self._subscribed = False
                
                self.logger.debug("MQTT limpieza completada")
            except Exception as e:
                self.logger.debug(f"Error durante limpieza MQTT: {e}")
            
    def stop(self):
        """
        Detiene la conexión MQTT de forma segura.
        
        Puede llamarse desde cualquier thread para interrumpir el consumer.
        Garantiza desconexión limpia para evitar consumidores "fantasma".
        """
        self.logger.debug("Solicitando detención de MQTT consumer...")
        self._stop_requested = True
        
        # Forzar desconexión inmediata
        if self.client:
            try:
                # Desconectar primero para liberar recursos del broker
                self.client.disconnect()
                self.logger.debug("MQTT disconnect() llamado")
            except Exception as e:
                self.logger.debug(f"Error en disconnect(): {e}")
            
            try:
                # Luego detener el loop de red
                self.client.loop_stop()
            except Exception as e:
                self.logger.debug(f"Error en loop_stop(): {e}")
        
        self._connected = False
        self._subscribed = False
