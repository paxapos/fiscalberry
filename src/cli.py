#!/usr/bin/env python3
import time
import os, asyncio
import threading

from common.fiscalberry_logger import getLogger
logger = getLogger()
from common.service_controller import ServiceController



if __name__ == "__main__":
    try:
        ServiceController().start()
    except Exception as e:
        logger.error(f"Error occurred: {e}", exc_info=True)
        os._exit(1)
