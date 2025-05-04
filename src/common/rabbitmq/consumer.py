import threading, os, pika
import queue

from common.ComandosHandler import ComandosHandler, TraductorException
from common.fiscalberry_logger import getLogger
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

        self.logger = getLogger()
        
    
    def connect(self):
        """Conecta al servidor RabbitMQ."""
        self.logger.info(f"Connecting to RabbitMQ server: {self.host}:{self.port}")

        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.host, port=self.port, virtual_host=self.vhost, credentials=pika.PlainCredentials(self.user, self.password)))

        #self.connection = pika.BlockingConnection(pika.ConnectionParameters(host="your-rabbitmq-server"))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.queue)
        self.channel.queue_bind(exchange=self.STREAM_NAME, queue=self.queue, routing_key=self.queue)


    def start(self):
        
        self.connect()

        def callback(ch, method, properties, body):
            
            self.message_queue.put(body)  # Enviar mensaje a la cola compartida
            
            try:
                comandoHandler = ComandosHandler()
                comandoHandler.send_command(body)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except TraductorException as e:
                self.logger.error(f"TraductorException Error al procesar mensaje: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                self.logger.error(traceback.format_exc())

            except Exception as e:
                self.logger.error(f"Error al procesar mensaje: {e}")
                self.logger.error(traceback.format_exc())
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            

        self.channel.basic_consume(queue=self.queue, on_message_callback=callback, auto_ack=False)
        self.logger.info(f"Waiting for messages in queue: {self.queue}")
        self.channel.start_consuming()

    def stop(self):
        """Detiene la conexión."""
        if self.connection:
            self.connection.close()
        
