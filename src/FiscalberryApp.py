import asyncio
from sio_handler import start
from Traductores.TraductoresHandler import TraductoresHandler, TraductorException
import Configberry
from fiscalberry_logger import getLogger


logger = getLogger()

class FiscalberryApp:

    sio = None

    def __init__(self):
        logger.info("Preparando Fiscalberry Server")

        self.configberry = Configberry.Configberry()
        serverUrl = self.configberry.config.get("SERVIDOR","sio_host", fallback="")
        uuid = self.configberry.config.get("SERVIDOR","uuid")
        
        asyncio.run(start(serverUrl, uuid))
        