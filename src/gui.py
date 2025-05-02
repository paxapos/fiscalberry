import subprocess
from threading import Thread
from ui.fiscalberry_app import FiscalberryApp
from kivy.properties import BooleanProperty,StringProperty
from common.Configberry import Configberry
from common.token_manager import get_token
from common.fiscalberry_logger import getLogger
logger = getLogger()

class ServiceController:
    """Controla el inicio y detención del servicio."""
    def __init__(self):
        self.process = None
        
    def is_service_running(self):
        """Verifica si el servicio ya está en ejecución."""
        if self.process and self.process.poll() is None:
            return True  # El proceso está en ejecución
        return False
    
    def toggle_service(self):
        """Alterna el estado del servicio."""
        if self.is_service_running():
            self.stop_service()
        else:
            self.start_service()

    def start_service(self):
        """Inicia el servicio en un subproceso."""
        if self.is_service_running():
            logger.info("El servicio ya está en ejecución.")
            return

        try:
            self.process = subprocess.Popen(["python3", "cli.py"])
            logger.info("Servicio iniciado.")
        except Exception as e:
            logger.error(f"Error al iniciar el servicio cli.py: {e}")


    def stop_service(self):
        """Detiene el servicio si está en ejecución."""
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
            logger.info("Servicio detenido.")

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
        Thread(target=service_controller.start_service).start()
        self.service_running = True  # Actualizar el estado del servicio


    def on_stop_service(self):
        """Llamado desde la GUI para detener el servicio."""
        service_controller.stop_service()
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