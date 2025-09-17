import os, pika, traceback, time
import queue

from fiscalberry.common.ComandosHandler import ComandosHandler, TraductorException
from fiscalberry.common.fiscalberry_logger import getLogger
from typing import Optional


class RabbitMQConsumer:
    
    STREAM_NAME = "paxaprinter"
    
    # 5GB
    STREAM_RETENTION = 5000000000
    
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
        self.logger = getLogger("RabbitMQ.Consumer")
        
        self.logger.info("=== Inicializando RabbitMQ Consumer ===")
        self.logger.info(f"Host: {host}:{port}")
        self.logger.info(f"Usuario: {user}")
        self.logger.info(f"VHost: {vhost}")
        self.logger.info(f"Cola: {queue_name}")
        
        self.host = host
        self.port = port
        self.user = user
        self.vhost = vhost
        self.password = password
        self.connection = None
        self.channel = None
        self.queue = queue_name
        self.message_queue = message_queue
        
        # Configuro logger según ambiente
        environment = os.getenv('ENVIRONMENT', 'production')
        if environment == 'development':
            sioLogger = True
        else:
            sioLogger = False

        self.logger.debug(f"Entorno: {environment}, Logging detallado: {sioLogger}")
        
    
    def connect(self):
        """Conecta al servidor RabbitMQ."""
        self.logger.info(f"=== CONECTANDO A RABBITMQ ===")
        self.logger.info(f"Servidor: {self.host}:{self.port}")
        self.logger.debug(f"Parámetros de conexión - Usuario: {self.user}, VHost: {self.vhost}")

        try:
            # Use connection parameters with shorter timeouts for faster failure detection
            self.logger.debug("Configurando parámetros de conexión...")
            params = pika.ConnectionParameters(
                host=self.host, 
                port=self.port, 
                virtual_host=self.vhost, 
                credentials=pika.PlainCredentials(self.user, self.password),
                heartbeat=600,
                blocked_connection_timeout=300,
                socket_timeout=5,  # Timeout más agresivo para detectar errores más rápido
                connection_attempts=1,  # Solo un intento, el retry lo maneja process_handler
                retry_delay=0.5  # Delay más corto entre intentos
            )
            
            self.logger.debug("Creando conexión blocking...")
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            self.logger.info("Canal RabbitMQ creado exitosamente")
            
            # Manejo del exchange
            self.logger.debug(f"Verificando si existe exchange '{self.STREAM_NAME}'...")
            try:
                # Verificar si el exchange existe sin intentar modificarlo
                self.channel.exchange_declare(
                    exchange=self.STREAM_NAME,
                    passive=True  # Solo verifica si existe, no intenta declararlo
                )
                self.logger.info(f"Exchange '{self.STREAM_NAME}' ya existe")
            except pika.exceptions.ChannelClosedByBroker as e:
                self.logger.warning(f"Exchange no existe, creando nuevo: {e}")
                # Si el exchange no existe, reconectamos y lo creamos
                self.connection = pika.BlockingConnection(params)
                self.channel = self.connection.channel()
                
                self.channel.exchange_declare(
                    exchange=self.STREAM_NAME,
                    exchange_type='direct',  # Usar direct como tipo predeterminado
                    durable=True
                )
                self.logger.info(f"Exchange '{self.STREAM_NAME}' creado como direct")
            
            self.logger.info(f"Conectado con RabbitMQ exitosamente")
            self.logger.info(f"Configurando cola: '{self.queue}'...")
            
        except Exception as e:
            self.logger.error(f"Error durante conexión a RabbitMQ: {e}", exc_info=True)
            raise

        # Manejo de la cola - verificar primero si existe
        try:
            # Verificar si la cola existe sin intentar modificarla
            self.channel.queue_declare(
                queue=self.queue,
                passive=True  # Solo verifica si existe, no intenta declararla
            )
            self.logger.info(f"Cola {self.queue} ya existe, usando configuración existente")
        except pika.exceptions.ChannelClosedByBroker:
            # Si la cola no existe o hay problemas con el canal, reconectamos
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            
            # Declarar la cola ahora que sabemos que no existe o fue eliminada
            self.channel.queue_declare(
                queue=self.queue, 
                durable=True  # Crear como durable si es una nueva cola
            )
            self.logger.info(f"Cola {self.queue} creada como durable")
        
        # Binding - intentar con la cola como routing key
        try:
            self.channel.queue_bind(
                exchange=self.STREAM_NAME, 
                queue=self.queue, 
                routing_key=self.queue  # Usar el nombre de la cola como routing key
            )
            self.logger.info(f"Cola {self.queue} enlazada a exchange {self.STREAM_NAME}")
        except pika.exceptions.ChannelClosedByBroker as e:
            self.logger.error(f"Error al enlazar cola: {e}")
            # Reconectar para seguir operando
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
        
        self.logger.info(f"Connected to RabbitMQ and bound queue {self.queue} to exchange {self.STREAM_NAME}")


    def start(self):
        self.connect()

        def callback(ch, method, properties, body):
            self.logger.debug(f"Received message in queue {self.queue}")
            start_time = time.time()

            try:
                # Parsing optimizado del mensaje
                if isinstance(body, bytes):
                    body_str = body.decode('utf-8')
                else:
                    body_str = body

                # Log optimizado - solo para debug y truncado
                self.logger.debug(f"Message: {body_str[:50]}...")

                # Parse JSON más eficiente
                try:
                    import json
                    json_data = json.loads(body_str)
                except json.JSONDecodeError:
                    self.logger.warning("Non-JSON message, processing as string")
                    json_data = body_str

                # Procesar mensaje de forma optimizada
                comandoHandler = ComandosHandler()
                result = comandoHandler.send_command(json_data)
                
                processing_time = time.time() - start_time
                
                # Verificar errores y acknowledment más rápido
                if "err" in result:
                    self.logger.error(f"Command error: {result['err']}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    return
                    
                # Acknowledge inmediato para mayor throughput
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
                # Log optimizado solo para trabajos lentos
                if processing_time > 1.0:
                    self.logger.warning(f"Slow message processed in {processing_time:.2f}s")
                else:
                    self.logger.debug(f"Message processed in {processing_time:.2f}s")

            except TraductorException as e:
                self.logger.error(f"Translator error: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            except Exception as e:
                self.logger.error(f"Processing error: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                
                
                
        # Configurar QoS para procesamiento más rápido - permitir más mensajes concurrentes
        self.channel.basic_qos(prefetch_count=5)  # Aumentado de 1 a 5 para mayor throughput
        self.channel.basic_consume(queue=self.queue, on_message_callback=callback, auto_ack=False)
        self.logger.info(f"Waiting for messages in queue: {self.queue}")

        try:
            self.channel.start_consuming()
        except Exception as e:
            self.logger.error(f"Error in consumer: {e}")
            self.logger.error(traceback.format_exc())
            # Try to reconnect
            self.stop()
            raise


    def stop(self):
        """Detiene la conexión."""
        if self.connection:
            self.connection.close()

