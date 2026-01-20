import os, pika, traceback
import queue
import time

from fiscalberry.common.ComandosHandler import ComandosHandler, TraductorException
from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.rabbitmq.error_publisher import publish_error
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
        
        self.logger.debug(f"RabbitMQ Consumer: {host}:{port} queue={queue_name}")
        
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

        
    def connect(self):
        """Conecta al servidor RabbitMQ."""
        try:
            params = pika.ConnectionParameters(
                host=self.host, 
                port=self.port, 
                virtual_host=self.vhost, 
                credentials=pika.PlainCredentials(self.user, self.password),
                heartbeat=30,
                blocked_connection_timeout=15,
                socket_timeout=5,
                connection_attempts=1,
                retry_delay=0.5
            )
            
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            
            # Exchange
            try:
                self.channel.exchange_declare(exchange=self.STREAM_NAME, passive=True)
            except pika.exceptions.ChannelClosedByBroker:
                self.connection = pika.BlockingConnection(params)
                self.channel = self.connection.channel()
                self.channel.exchange_declare(exchange=self.STREAM_NAME, exchange_type='direct', durable=True)
            
        except Exception as e:
            self.logger.error(f"Error RabbitMQ: {e}")
            raise

        # Cola
        try:
            self.channel.queue_declare(queue=self.queue, passive=True)
        except pika.exceptions.ChannelClosedByBroker:
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=self.queue, durable=True)
        
        # Binding
        try:
            self.channel.queue_bind(exchange=self.STREAM_NAME, queue=self.queue, routing_key=self.queue)
        except pika.exceptions.ChannelClosedByBroker as e:
            self.logger.error(f"Error bind: {e}")
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
        
        self.logger.debug(f"RabbitMQ conectado: queue={self.queue}")


    def start(self):
        self.connect()

        def callback(ch, method, properties, body):
            start_time = time.time()

            try:
                # Parsing optimizado del mensaje
                if isinstance(body, bytes):
                    body_str = body.decode('utf-8')
                else:
                    body_str = body

                # Log optimizado - solo para debug y truncado

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
                    error_msg = result['err']
                    self.logger.error("Command execution failed: %s", error_msg)
                    
                    # Publicar error a RabbitMQ
                    publish_error(
                        error_type="COMMAND_EXECUTION_ERROR",
                        error_message=error_msg,
                        context={
                            "command": json_data,
                            "result": result,
                            "queue": self.queue
                        }
                    )
                    
                    # Si es un error recuperable, podríamos reintentar o poner en una cola de espera
                    # Por ahora, consideramos que es un error y no reconocemos el mensaje
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    return
                    

                # Acknowledge the message ONLY after successful processing
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
                # Log optimizado solo para trabajos lentos
                if processing_time > 1.0:
                    self.logger.warning(f"Slow message processed in {processing_time:.2f}s")

            except TraductorException as e:
                self.logger.error("Translation error: %s", e)
                
                # Publicar error a RabbitMQ
                publish_error(
                    error_type="TRANSLATOR_ERROR",
                    error_message=str(e),
                    context={
                        "command": body_str[:500] if isinstance(body_str, str) else str(body)[:500],
                        "queue": self.queue
                    },
                    exception=e
                )
                
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                
            except json.JSONDecodeError as e:
                self.logger.error("JSON decode error: %s", e)
                
                # Publicar error a RabbitMQ
                publish_error(
                    error_type="JSON_DECODE_ERROR",
                    error_message=f"Invalid JSON format: {str(e)}",
                    context={
                        "raw_body": body_str[:500] if isinstance(body_str, str) else str(body)[:500],
                        "queue": self.queue
                    },
                    exception=e
                )
                
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                
            except Exception as e:
                self.logger.error("Message processing error: %s", e)
                
                # Publicar error a RabbitMQ
                publish_error(
                    error_type="PROCESSING_ERROR",
                    error_message=f"Error processing message: {str(e)}",
                    context={
                        "raw_body": body_str[:500] if 'body_str' in locals() else str(body)[:500],
                        "queue": self.queue
                    },
                    exception=e
                )
                
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

