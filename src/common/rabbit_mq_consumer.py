#!/usr/bin/env python

import threading, os, pika

from common.ComandosHandler import ComandosHandler, TraductorException
from common.fiscalberry_logger import getLogger


class RabbitMQConsumer:
    
    STREAM_NAME = "paxaprinter"
    
    # 5GB
    STREAM_RETENTION = 5000000000
    
    def __init__(self, host, port, user, password, queue, vhost="/"):
        self.host = host
        self.port = port
        self.user = user
        self.vhost = vhost
        self.password = password
        self.connection = None
        self.channel = None
        self.queue = queue
        
        # Configuro logger según ambiente
        environment = os.getenv('ENVIRONMENT', 'production')
        if environment == 'development':
            sioLogger = True
        else:
            sioLogger = False

        self.logger = getLogger()
        
        

    def start(self):
        
        print(f"Connecting to RabbitMQ server: {self.host}:{self.port}")
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.host, port=self.port, virtual_host=self.vhost, credentials=pika.PlainCredentials(self.user, self.password)))
        channel = connection.channel()
        
        #channel.exchange_declare(exchange=self.STREAM_NAME, exchange_type='direct')
        queue_name = self.queue
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=self.STREAM_NAME, queue=queue_name, routing_key=self.queue)

        def callback(ch, method, properties, body):
            try:
                comandoHandler = ComandosHandler()
                comandoHandler.send_command(body)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except TraductorException as e:
                self.logger.error(f"TraductorException Error al procesar mensaje: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            except Exception as e:
                self.logger.error(f"Error al procesar mensaje: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            

        channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)
        print(f"Waiting for messages in queue: {queue_name}")
        channel.start_consuming()

    
        
