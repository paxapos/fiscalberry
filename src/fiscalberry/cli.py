#!/usr/bin/env python3
import time
import os, asyncio
import threading

from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger()
from fiscalberry.common.service_controller import ServiceController

def main():
    try:
        ServiceController().start()
    except Exception as e:
        logger.error(f"Error occurred: {e}", exc_info=True)
        os._exit(1)

if __name__ == "__main__":
    main()
    
