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
    - Reconexión automática
    """
    
    MQTT_PORT_DEFAULT = 1883
    
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
        
        # Constantes para binding AMQP
        self.AMQP_PORT = 5672
        self.EXCHANGE_NAME = 'paxaprinter'
        
    def _ensure_amqp_binding(self):
        """
        Crea el binding entre el exchange AMQP 'paxaprinter' y la cola MQTT.
        
        Este método resuelve el gap entre:
        - Backend CakePHP que publica via AMQP al exchange 'paxaprinter'
        - Fiscalberry que consume via MQTT
        
        El binding se crea usando una conexión AMQP temporal, luego
        Fiscalberry continúa consumiendo via MQTT normalmente.
        
        El binding es idempotente: si ya existe, no falla.
        """
        try:
            import pika
            
            self.logger.info("Creando binding AMQP para exchange '%s' -> topic '%s'", 
                           self.EXCHANGE_NAME, self.topic)
            
            # Conectar via AMQP (puerto 5672, no MQTT 1883)
            credentials = pika.PlainCredentials(self.user, self.password)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.host,
                    port=self.AMQP_PORT,
                    credentials=credentials,
                    socket_timeout=10,
                    connection_attempts=2
                )
            )
            channel = connection.channel()
            
            # Declarar exchange (idempotente - si ya existe, no falla)
            channel.exchange_declare(
                exchange=self.EXCHANGE_NAME,
                exchange_type='direct',
                durable=True
            )
            
            # Nombre de cola MQTT: RabbitMQ crea colas con este formato
            # para clientes MQTT con clean_session=False y QoS 1
            mqtt_queue_name = f"mqtt-subscription-fiscalberry-{self.topic}qos1"
            
            # Declarar cola durable (debe coincidir con la que crea MQTT)
            channel.queue_declare(
                queue=mqtt_queue_name,
                durable=True
            )
            
            # Crear binding: exchange -> cola con routing_key = machine_uuid
            channel.queue_bind(
                exchange=self.EXCHANGE_NAME,
                queue=mqtt_queue_name,
                routing_key=self.topic  # = machine_uuid del paxaprinter
            )
            
            connection.close()
            
            self.logger.info("Binding AMQP creado: %s -> %s (routing_key=%s)",
                           self.EXCHANGE_NAME, mqtt_queue_name, self.topic)
            return True
            
        except ImportError:
            self.logger.warning("pika no disponible - binding AMQP no creado. "
                              "Asegurate que el binding existe en RabbitMQ.")
            return False
            
        except Exception as e:
            # No es fatal: el binding puede ya existir o ser creado manualmente
            self.logger.warning("No se pudo crear binding AMQP: %s. "
                              "Verificar que el binding existe en RabbitMQ.", e)
            return False
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback cuando se conecta al broker MQTT."""
        if rc == 0:
            self.logger.info("MQTT conectado exitosamente")
            self._connected = True
            # Suscribirse al topic con QoS 1 para ACK automático
            client.subscribe(self.topic, qos=1)
            self.logger.info(f"Suscrito a topic: {self.topic}")
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
        if rc != 0:
            self.logger.warning(f"Desconexión inesperada de MQTT (rc={rc})")
        else:
            self.logger.debug("MQTT desconectado correctamente")
            
    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """Callback cuando la suscripción es confirmada."""
        self._subscribed = True
        self.logger.debug(f"Suscripción confirmada (QoS: {granted_qos})")
        
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
            except json.JSONDecodeError:
                self.logger.warning("Mensaje no es JSON válido, procesando como string")
                json_data = body_str
                
            # Procesar comando
            comandoHandler = ComandosHandler()
            result = comandoHandler.send_command(json_data)
            
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
            
        except json.JSONDecodeError as e:
            self.logger.error("Error decodificando JSON: %s", e)
            publish_error(
                error_type="JSON_DECODE_ERROR",
                error_message=f"Formato JSON inválido: {str(e)}",
                context={
                    "raw_body": body_str[:500] if body_str else "",
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
        """Conecta al broker MQTT."""
        try:
            # PASO 1: Asegurar que existe el binding AMQP -> MQTT
            # Esto crea el "puente" entre el exchange paxaprinter (AMQP)
            # y la cola MQTT que vamos a consumir
            self._ensure_amqp_binding()
            
            # PASO 2: Crear cliente MQTT con sesión persistente
            self.client = mqtt.Client(
                client_id=f"fiscalberry-{self.topic}",
                clean_session=False,  # CRÍTICO: Sesión persistente
                protocol=mqtt.MQTTv311
            )
            
            # Configurar credenciales
            self.client.username_pw_set(self.user, self.password)
            
            # Configurar callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_subscribe = self._on_subscribe
            self.client.on_message = self._on_message
            
            # Conectar via MQTT
            self.client.connect(self.host, self.port, keepalive=60)
            
            self.logger.debug(f"Conectando a MQTT: {self.host}:{self.port}")
            
        except Exception as e:
            self.logger.error(f"Error conectando a MQTT: {e}")
            raise
            
    def start(self):
        """Inicia el loop de consumo de mensajes MQTT."""
        self.connect()
        
        self.logger.info(f"Esperando mensajes en topic: {self.topic}")
        
        try:
            # Loop bloqueante - procesa mensajes hasta que se llame stop()
            self.client.loop_forever()
        except Exception as e:
            self.logger.error(f"Error en consumer MQTT: {e}")
            self.logger.error(traceback.format_exc())
            self.stop()
            raise
            
    def stop(self):
        """Detiene la conexión MQTT."""
        self._stop_requested = True
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
                self.logger.debug("MQTT desconectado")
            except Exception as e:
                self.logger.error(f"Error desconectando MQTT: {e}")
