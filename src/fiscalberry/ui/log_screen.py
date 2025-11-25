# ============================================
# ARCHIVO: src/fiscalberry/ui/log_screen.py
# ============================================

from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty
from kivy.clock import Clock
from fiscalberry.common.fiscalberry_logger import getLogFilePath
import platform
import os
import subprocess

class LogScreen(Screen):
    logs = StringProperty("")
    logFilePath = StringProperty("")
    
    def on_kv_post(self, base_widget):
        Clock.schedule_interval(self.update_logs, 1)
    
    def open_log_file(self):
        """Abre el archivo de log en el editor de texto predeterminado."""
        if self.logFilePath:
            try:
                system = platform.system()
                if system == "Windows":
                    os.startfile(self.logFilePath)
                elif system == "Darwin":
                    subprocess.Popen(["open", self.logFilePath])
                else:
                    subprocess.Popen(["xdg-open", self.logFilePath])
            except FileNotFoundError:
                self.logs = f"Error: No se encontró el archivo de log en {self.logFilePath}"
            except OSError as e:
                self.logs = f"Error al abrir el log con la aplicación predeterminada: {e}"
            except Exception as e:
                self.logs = f"Error inesperado al abrir el log: {e}"
        else:
            self.logs = "No se ha encontrado la ruta del archivo de log."
    
    def update_logs(self, dt):
        """Lee el archivo de logs y actualiza la propiedad `logs`."""
        self.logFilePath = getLogFilePath()
        try:
            with open(self.logFilePath, "r") as log_file:
                log_data = log_file.read()
                self.logs = log_data
                if "scroll_view" in self.ids:
                    self.ids.scroll_view.scroll_y = 0
        except Exception as e:
            self.logs = f"Error al leer log: {e}"