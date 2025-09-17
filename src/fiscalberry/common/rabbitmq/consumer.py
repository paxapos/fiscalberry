import os, pika, traceback
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
                socket_timeout=10,  # Timeout más corto para detectar errores de red rápidamente
                connection_attempts=1,  # Solo un intento, el retry lo maneja process_handler
                retry_delay=1  # Delay corto entre intentos
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
            self.logger.info(f"Received message in queue {self.queue}")

            try:
                # Parse the message body - it might be bytes and need decoding
                if isinstance(body, bytes):
                    body_str = body.decode('utf-8')
                else:
                    body_str = body

                # Log the raw message for debugging
                self.logger.info(f"Message content: {body_str[:100]}...")  # Log first 100 chars

                # Try to parse as JSON if needed
                try:
                    import json
                    json_data = json.loads(body_str)
                    self.logger.info("Successfully parsed message as JSON")
                except json.JSONDecodeError:
                    self.logger.warning("Message is not valid JSON, passing as raw string")
                    json_data = body_str

                # Process the message
                comandoHandler = ComandosHandler()
                result = comandoHandler.send_command(json_data)
                
                # Verificar si hay un error en la respuesta
                if "err" in result:
                    self.logger.error(f"Error in command handler: {result['err']}")
                    # Si es un error recuperable, podríamos reintentar o poner en una cola de espera
                    # Por ahora, consideramos que es un error y no reconocemos el mensaje
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    return
                    
                self.logger.info(f"Command handler result: {result}")

                # Acknowledge the message ONLY after successful processing
                ch.basic_ack(delivery_tag=method.delivery_tag)

            except TraductorException as e:
                self.logger.error(f"TraductorException Error: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                self.logger.error(traceback.format_exc())
            except Exception as e:
                self.logger.error(f"Error processing message: {e}")
                self.logger.error(traceback.format_exc())
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                
                
                
        # Set prefetch count to process one message at a time
        self.channel.basic_qos(prefetch_count=1)
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

