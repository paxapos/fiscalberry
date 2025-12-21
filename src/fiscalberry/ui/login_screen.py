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
ADOP_LINK = host + "/adopt/" + uuid
class LoginScreen(Screen):
    errorMsg = StringProperty("")
    adoptarLink = StringProperty(ADOP_LINK)
    qrCodeLink = StringProperty(QRGENLINK + ADOP_LINK)
    
    
    def on_leave(self, *args):
        """Se llama automáticamente cuando se sale de la pantalla."""
        self.errorMsg = ""
    
    def login(self, username, password):
        """Autentica al usuario contra el backend."""
        backend_url = host.rstrip("/") + "/login.json"
        try:
            if do_login(username, password):
                # Login exitoso
                app = App.get_running_app()
                app.root.current = "main"
                return True
            else:
                # Login fallido
                logger.error("Error de autenticación.")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al conectar con el backend: {e}")
            self.errorMsg = f"Error de conexión: {e}"
            return False
        except Exception as e:
            logger.error(f"Error de autenticación: {e}")
            self.errorMsg = str(e)
            return False
        
        
    
        
        

    def save_token(self, token):
        """Guarda el token JWT en un archivo local."""
        return save_token(token)
    
    def get_sites(self):
        """Obtiene los sitios del usuario autenticado."""
        backend_url = host.rstrip("/") + "/sites.json"
        try:
            response = requests.get(backend_url, headers={"Authorization": f"Bearer {self.load_token()}"})
            logger.debug(f"Response: {response.status_code}")
            if response.status_code == 200:
                return response.json()
            else:
                logger.error("Error al obtener los sitios.")
                return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al conectar con el backend: {e}")
            return []



