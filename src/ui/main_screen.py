from kivy.uix.screenmanager import Screen
from kivy.app import App  # Import the App class
import os
from common.token_manager import delete_token
from kivy.properties import StringProperty
from os.path import join, dirname

class MainScreen(Screen):
    stop_image = StringProperty(join(dirname(__file__), "assets/stop.png"))
    play_image = StringProperty(join(dirname(__file__), "assets/play.png"))
    
    connected_image = StringProperty(join(dirname(__file__), "assets/connected.png"))
    disconnected_image = StringProperty(join(dirname(__file__), "assets/disconnected.png"))
    
    def start_service(self):
        """Inicia el servicio desde la GUI."""
        app = App.get_running_app()  # Use App.get_running_app()
        app.on_start_service()
        
    def toggle_service(self):
        """Alterna el estado del servicio desde la GUI."""
        app = App.get_running_app()
        app.on_toggle_service()

    def stop_service(self):
        """Detiene el servicio desde la GUI."""
        app = App.get_running_app()  # Use App.get_running_app()
        app.on_stop_service()

    def logout(self):
        """Cierra sesión y elimina el token JWT."""
        delete_token()

        app = App.get_running_app()  # Use App.get_running_app()
        app.root.current = "login"