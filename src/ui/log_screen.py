from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty
from kivy.clock import Clock
from common.fiscalberry_logger import getLogFilePath

class LogScreen(Screen):
    logs = StringProperty("")  # Propiedad para almacenar los logs

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_interval(self.update_logs, 1)  # Actualizar los logs cada segundo

    def update_logs(self, dt):
        """Lee el archivo de logs y actualiza la propiedad `logs`."""
        logFilePath = getLogFilePath()
        try:
            with open(logFilePath, "r") as log_file:
                self.logs = log_file.read()
                # Forzar el scroll hacia abajo
                scroll_view = self.ids.scroll_view  # Obtener el ScrollView por ID
                scroll_view.scroll_y = 0  # Mover el scroll hacia abajo
        except FileNotFoundError:
            self.logs = "No se encontró el archivo de logs."