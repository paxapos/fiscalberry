#!/usr/bin/env python

import threading, os, pika

from common.ComandosHandler import ComandosHandler, TraductorException
from common.fiscalberry_logger import getLogger


class RabbitMQConsumer:
    
    STREAM_NAME = "paxaprinter"
    
    # 5GB
    STREAM_RETENTION = 5000000000
    
    def __init__(self, host, port, user, password, uuid):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.connection = None
        self.channel = None
        
        self.client_uuid = uuid
        
        # Configuro logger según ambiente
        environment = os.getenv('ENVIRONMENT', 'production')
        if environment == 'development':
            sioLogger = True
        else:
            sioLogger = False

        self.logger = getLogger()
        
        

    def start(self):
        
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.host, port=self.port, credentials=pika.PlainCredentials(self.user, self.password)))
        channel = connection.channel()
        
        #channel.exchange_declare(exchange=self.STREAM_NAME, exchange_type='direct')
        queue_name = self.client_uuid
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=self.STREAM_NAME, queue=queue_name, routing_key=self.client_uuid)

        def callback(ch, method, properties, body):
            comandoHandler = ComandosHandler()
            comandoHandler.send_command(body)

        channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
        print(f"Waiting for messages in queue: {queue_name}")
        channel.start_consuming()

    
        
