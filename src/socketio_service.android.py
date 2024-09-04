import time
from jnius import autoclass
from android import AndroidService

import time


# importo el modulo que se encarga de la comunicacion con el servidor
from fiscalberry_sio import FiscalberrySio
from common.discover import send_discover_in_thread
from common.Configberry import Configberry



# Importar las clases necesarias de Android
PythonService = autoclass('org.kivy.android.PythonService')
Notification = autoclass('android.app.Notification')
PendingIntent = autoclass('android.app.PendingIntent')
Intent = autoclass('android.content.Intent')

class FiscalberryService:
    def __init__(self):
        self.service = AndroidService('Fiscal Service', 'Running')
        self.service.start('Fiscal Service Running')
        self.run()

    def run(self):
        configberry = Configberry()

        while True:
            serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
            uuid = configberry.config.get("SERVIDOR", "uuid")
            send_discover_in_thread()
            sio = FiscalberrySio(serverUrl, uuid)
            sio.start()
            time.sleep(5)

if __name__ == '__main__':
    FiscalberryService()