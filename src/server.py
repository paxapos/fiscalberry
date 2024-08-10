#!/usr/bin/env python3
# coding=utf-8

from multiprocessing import freeze_support
from fiscalberry_logger import getLogger
import Configberry
from sio_handler import start
import asyncio

logger = getLogger()


def main():
    logger.info("Preparando Fiscalberry Server")

    configberry = Configberry.Configberry()
    serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
    uuid = configberry.config.get("SERVIDOR", "uuid")

    asyncio.run(start(serverUrl, uuid))


if __name__ == "__main__":
    freeze_support()
    main()
