import os
import requests
import json
from kivy.uix.screenmanager import Screen
from kivy.app import App
import tempfile
from fiscalberry.common.token_manager import save_token, do_login
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.fiscalberry_logger import getLogger
from kivy.properties import StringProperty

logger = getLogger()
configberry = Configberry()

host = configberry.get("SERVIDOR", "sio_host", "https://beta.paxapos.com")
uuid = configberry.get("SERVIDOR", "uuid", fallback="")

QRGENLINK = "https://codegenerator.paxapos.com/?bcid=qrcode&text="
# Asegurarse de que el host no termina con / y que el uuid esté completo
ADOP_LINK = host.rstrip("/") + "/adopt/" + uuid

class AdoptScreen(Screen):
    adoptarLink = StringProperty(ADOP_LINK)
    qrCodeLink = StringProperty(QRGENLINK + ADOP_LINK)
    
    def on_enter(self):
        """Se llama cuando se entra a la pantalla - actualiza los links por si cambió la config"""
        configberry = Configberry()
        host = configberry.get("SERVIDOR", "sio_host", "https://beta.paxapos.com")
        uuid = configberry.get("SERVIDOR", "uuid", fallback="")
        
        # Reconstruir los links con valores actualizados
        adopt_link = host.rstrip("/") + "/adopt/" + uuid
        self.adoptarLink = adopt_link
        self.qrCodeLink = QRGENLINK + adopt_link
        
        # Log para debug
        logger.info(f"AdoptScreen - Host: {host}")
        logger.info(f"AdoptScreen - UUID: {uuid}")
        logger.info(f"AdoptScreen - Link completo: {adopt_link}")