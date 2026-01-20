from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty
from kivy.clock import Clock
from fiscalberry.common.fiscalberry_logger import getLogFilePath
import platform
import os
import subprocess
class LogScreen(Screen):
    logs = StringProperty("")  # Propiedad para almacenar los logs
    logFilePath = StringProperty("", allownone=True)  # Propiedad para almacenar la ruta del log
  
    def on_kv_post(self, base_widget):
        # Se garantiza que los ids están disponibles
        Clock.schedule_interval(self.update_logs, 1)  # Actualizar cada segundo


    def open_log_file(self):
        """Abre el archivo de log en el editor de texto predeterminado."""
        # Verificar que hay una ruta válida (no None ni vacía)
        if self.logFilePath and self.logFilePath.strip():

            try:
                system = platform.system()
                if system == "Windows":
                    # os.startfile opens the file with the default application on Windows
                    os.startfile(self.logFilePath)
                elif system == "Darwin":  # macOS
                    subprocess.Popen(["open", self.logFilePath])
                else:  # Linux and other Unix-like systems
                    # xdg-open opens the file with the default application on Linux
                    subprocess.Popen(["xdg-open", self.logFilePath])
            except FileNotFoundError:
                self.logs = f"Error: No se encontró el archivo de log en {self.logFilePath}"
            except OSError as e:
                # Catch errors like 'xdg-open' or 'open' not found, or no default app associated
                self.logs = f"Error al abrir el log con la aplicación predeterminada: {e}"
            except Exception as e:
                self.logs = f"Error inesperado al abrir el log: {e}"
        else:
            self.logs = "No se ha encontrado la ruta del archivo de log."

    def update_logs(self, dt):
        """Lee el archivo de logs y actualiza la propiedad `logs`."""
        # Obtener ruta del log (puede ser None)
        log_path = getLogFilePath()
        
        # Convertir None a string vacío para evitar crash con StringProperty
        self.logFilePath = log_path if log_path else ""
        
        # Si no hay archivo de log configurado, mostrar mensaje
        if not self.logFilePath:
            self.logs = "No hay archivo de log configurado.\nLos logs se muestran solo en consola."
            return
        
        try:
            with open(self.logFilePath, "r") as log_file:
                log_data = log_file.read()  # Leer contenido del log
                self.logs = log_data
                # Actualizar el scroll si existe el ScrollView
                if "scroll_view" in self.ids:
                    self.ids.scroll_view.scroll_y = 0
        except Exception as e:
            self.logs = f"Error al leer log: {e}"