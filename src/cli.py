#!/usr/bin/env python3
# coding=utf-8
import asyncio
import time
from multiprocessing import freeze_support


from sio_handler import start
from common.discover import send_discover
from common.fiscalberry_logger import getLogger
from common.Configberry import Configberry

logger = getLogger()


def main():
    freeze_support()

    while True:
        logger.info("Preparando Fiscalberry Server")

        configberry = Configberry()
        serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
        uuid = configberry.config.get("SERVIDOR", "uuid")
        send_discover()
        start(serverUrl, uuid)

        logger.warning("Termino ejecucion de server socketio?.. reconectando en 5s")
        time.sleep(5)


if __name__ == "__main__":
    main()
