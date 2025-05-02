import os
import requests
import json
from kivy.uix.screenmanager import Screen
from kivy.app import App
import tempfile
from common.token_manager import save_token, do_login
from common.Configberry import Configberry
from common.fiscalberry_logger import getLogger
from kivy.properties import StringProperty

logger = getLogger()

configberry = Configberry()
host = configberry.get("SERVIDOR", "sio_host", "https://beta.paxapos.com")
uuid = configberry.get("SERVIDOR", "uuid", fallback="")

QRGENLINK = "https://codegenerator.paxapos.com/?bcid=qrcode&text="
ADOP_LINK = host + "/adopt/" + uuid
class AdoptScreen(Screen):
    adoptarLink = StringProperty(ADOP_LINK)
    qrCodeLink = StringProperty(QRGENLINK + ADOP_LINK)


