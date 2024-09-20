#!/usr/bin/env python3
import time
import os
import logging

from common.Configberry import Configberry

configberry = Configberry()

environment = configberry.config.get("SERVIDOR", "environment", fallback="production")

# configuro logger segun ambiente
if environment == 'development':
    print("* * * * * Modo de desarrollo * * * * *")
    logging.basicConfig(level=logging.DEBUG)
else:
    print("@ @ @ @ @ Modo de producción @ @ @ @ @")
    logging.basicConfig(level=logging.WARNING)


from common.fiscalberry_logger import getLogger
logger = getLogger()


# importo el modulo que se encarga de la comunicacion con el servidor
from common.rabbit_mq_consumer import RabbitMQConsumer
from common.discover import send_discover_in_thread
import asyncio



def start():
    logger.info("Iniciando Fiscalberry Server")

    uuid = configberry.config.get("SERVIDOR", "uuid")
    host = configberry.config.get("RabbitMq", "host", fallback="localhost")
    port = configberry.config.get("RabbitMq", "port", fallback="5672")
    user = configberry.config.get("RabbitMq", "user", fallback="guest")
    password = configberry.config.get("RabbitMq", "password", fallback="guest")
    #send_discover_in_thread()

    while True:

        sio = RabbitMQConsumer(host, port, user, password, uuid)
        # Inside the while loop
        sio.start()
        logger.warning("Termino ejecucion de server socketio?.. reconectando en 5s")
        time.sleep(5)


if __name__ == "__main__":
    start()
    