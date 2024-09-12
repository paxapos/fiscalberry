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
from common.fiscalberry_sio import FiscalberrySio
from common.discover import send_discover_in_thread



def start():

    while True:
        logger.info("Preparando Fiscalberry Server")

        serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
        uuid = configberry.config.get("SERVIDOR", "uuid")
        send_discover_in_thread()
        sio = FiscalberrySio(serverUrl, uuid)
        sio.start_print_server()
        logger.warning("Termino ejecucion de server socketio?.. reconectando en 5s")
        time.sleep(5)


if __name__ == "__main__":
    start()