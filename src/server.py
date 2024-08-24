#!/usr/bin/env python3
# coding=utf-8

from multiprocessing import freeze_support
from fiscalberry_app.discover import send_discover
from fiscalberry_logger import getLogger
import Configberry
from sio_handler import start
import asyncio
import time

logger = getLogger()



if __name__ == "__main__":
    freeze_support()

    while True:
        logger.info("Preparando Fiscalberry Server")

        configberry = Configberry.Configberry()
        serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
        uuid = configberry.config.get("SERVIDOR", "uuid")
        
        send_discover()
        
        start(serverUrl, uuid)

        logger.warning("Termino ejecucion de server socketio?.. reconectando en 5s")
        time.sleep(5)
