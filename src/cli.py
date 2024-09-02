#!/usr/bin/env python3
import asyncio
import time
from multiprocessing import freeze_support
import os
import logging

from dotenv import load_dotenv
load_dotenv()


# configuro logger segun ambiente
environment = os.getenv('ENVIRONMENT', 'production')
if environment == 'development':
    print("* * * * * Modo de desarrollo * * * * *")
    logging.basicConfig(level=logging.DEBUG)
else:
    print("@ @ @ @ @ Modo de producción @ @ @ @ @")
    logging.basicConfig(level=logging.WARNING)


from common.fiscalberry_logger import getLogger
logger = getLogger()


# importo el modulo que se encarga de la comunicacion con el servidor
from sio_handler import start
from common.discover import send_discover
from common.Configberry import Configberry



def main():
    freeze_support()
    configberry = Configberry()

    while True:
        logger.info("Preparando Fiscalberry Server")


        serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
        uuid = configberry.config.get("SERVIDOR", "uuid")
        send_discover()
        start(serverUrl, uuid)

        logger.warning("Termino ejecucion de server socketio?.. reconectando en 5s")
        time.sleep(5)


if __name__ == "__main__":
    main()
