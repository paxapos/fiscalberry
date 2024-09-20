#!/usr/bin/env python3
import time
import os, asyncio
import threading

from common.fiscalberry_logger import getLogger
logger = getLogger()


from common.Configberry import Configberry
configberry = Configberry()


# importo el modulo que se encarga de la comunicacion con el servidor
from common.discover import send_discover_in_thread


def startRabbit():
    from common.rabbit_mq_consumer import RabbitMQConsumer


    uuid = configberry.config.get("SERVIDOR", "uuid")
    host = configberry.config.get("RabbitMq", "host", fallback="localhost")
    port = configberry.config.get("RabbitMq", "port", fallback="5672")
    user = configberry.config.get("RabbitMq", "user", fallback="guest")
    password = configberry.config.get("RabbitMq", "password", fallback="guest")
    
    rb = RabbitMQConsumer(host, port, user, password, uuid)
    # Inside the while loop
    rb.start()
    logger.warning("Termino ejecucion de server socketio?.. reconectando en 5s")


def startSocketio():
    from common.fiscalberry_sio import FiscalberrySio
    serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
    uuid = configberry.config.get("SERVIDOR", "uuid")
    sio = FiscalberrySio(serverUrl, uuid)
    sio.start_print_server()
    logger.warning("Termino ejecucion de server socketio?.. reconectando en 5s")
    

def discover():
    send_discover_in_thread()
    logger.info("Discover enviado")
    

def start_services():
    logger.info("Iniciando Fiscalberry Server")

    # iniciar en 3 threads distintos los servicios
    discover_thread = threading.Thread(target=discover)
    socketio_thread = threading.Thread(target=startSocketio)
    rabbit_thread = threading.Thread(target=startRabbit)

    discover_thread.start()
    socketio_thread.start()
    rabbit_thread.start()

    discover_thread.join()
    socketio_thread.join()
    rabbit_thread.join()


if __name__ == "__main__":

    
    try:
        start_services()
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        os._exit(1)

    