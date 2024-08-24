import threading
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.clock import Clock
from dotenv import load_dotenv
from kivy.logger import Logger
import Configberry
import os

from fiscalberry_app.discover import send_discover
from fiscalberry_app.sio import start_socketio_client

load_dotenv()


configberry = Configberry.Configberry()
sio = None

class LogWidget(ScrollView):
    
    logs = []
    
    def __init__(self, **kwargs):
        super(LogWidget, self).__init__(**kwargs)        

        self.background_color = (1, 0.75, 0.8, 1)  # Set pink background color

    def add_log(self, log):     
        self.logs.append(log)
        self.update_logs()
        
    def update_logs(self):
        self.clear_widgets()
        for log in self.logs:
            self.add_widget(Label(text=log, size_hint_y=None, height=40))


class ConnectedImage(Image):
    source = "assets/disconnected.png"
    


class MainLayout(BoxLayout):
    
    def __init__(self, **kwargs):
        super(MainLayout, self).__init__(**kwargs)
        self.log_widget = LogWidget(size_hint=(1, 0.5))
        self.add_widget(self.log_widget)


class FiscalberryApp(App):

    sioServerUrl = os.environ.get("SIO_SERVER_URL")

    connected: bool = False

    def __init__(self, **kwargs):
        super(FiscalberryApp, self).__init__(**kwargs)
        self.sio = None

        # load APP config
        serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
        self.uuid = configberry.config.get("SERVIDOR", "uuid")
        self.uuidSmall = self.uuid[:8]

        self.sioServerUrl = serverUrl if serverUrl else self.sioServerUrl

    def build(self):
        self.root = MainLayout()
        self.log_widget = self.root.log_widget
        return self.root

    def add_log(self, text):
        self.log_widget.add_log(text)

    def store_new_host(self, value):
        host = value
        Logger.info(f"FiscalberryApp: vino para guardar sio_host:: {
                    host} antes estaba {self.sioServerUrl}")
        if host != self.sioServerUrl:
            Logger.info(f"FiscalberryApp: se guarda nuevo sio_host:: {host}")
            configberry.writeKeyForSection("SERVIDOR", "sio_host", host)

    
    def connect_to_server(self):        
        # Start the socketio thread
        sio = start_socketio_client(self)
        
    def send_discover(self):
        send_discover()
    
    def is_connected(self):
        return sio and sio.connected

    def on_start(self):
        """
        This function is executed when the application starts.
        It is a Kivy function.
        """

        # Iniciar con el ícono rojo por defecto
        Logger.info("FiscalberryApp: Iniciando la aplicación")
        
        # Create a new thread to execute the send_discover function
        t = threading.Thread(target=self.send_discover)
        t.start()

        # Conectarse automáticamente al iniciar la aplicación
        self.connect_to_server()
