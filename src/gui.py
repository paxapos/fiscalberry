import subprocess
from threading import Thread
from ui.fiscalberry_app import FiscalberryApp
from kivy.properties import BooleanProperty,StringProperty
from common.Configberry import Configberry
from common.token_manager import get_token
from common.fiscalberry_logger import getLogger
from common.service_controller import ServiceController
logger = getLogger()

service_controller = ServiceController()

configberry = Configberry()
uuid = configberry.get("SERVIDOR", "uuid", fallback="")
host = configberry.get("SERVIDOR", "sio_host")


class FiscalberryAppWithService(FiscalberryApp):
    service_running = BooleanProperty(False)  # Propiedad para rastrear el estado del servicio

    uuid = StringProperty(uuid)  # Propiedad para mostrar el UUID en la GUI
    host = StringProperty(host)  # Propiedad para mostrar el host en la GUI
    
    def on_toggle_service(self):
        """Llamado desde la GUI para alternar el estado del servicio."""
        service_controller.toggle_service()
        self.service_running = service_controller.is_service_running()

    def on_start_service(self):
        """Llamado desde la GUI para iniciar el servicio."""
        Thread(target=service_controller.start).start()
        self.service_running = True  # Actualizar el estado del servicio


    def on_stop_service(self):
        """Llamado desde la GUI para detener el servicio."""
        service_controller.stop()
        self.service_running = False  # Actualizar el estado del servicio

    def build(self):
        # Llama al método build de la clase base para configurar la GUI
        sm = super().build()

        # Inicia el servicio automáticamente
        token = get_token()
        if token:
            self.on_start_service()

        return sm

def main():
    FiscalberryAppWithService().run()

if __name__ == "__main__":
    main()