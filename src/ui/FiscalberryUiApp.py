import asyncio
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.properties import Property,BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock
from kivy.config import Config
from FiscalberryApp import FiscalberryApp
import Configberry
from SioClientHandler import SioClientHandler

# Establecer el tamaño de la ventana
Config.set('graphics', 'width', '200')
Config.set('graphics', 'height', '300')

class LayoutWidget(Widget):
    pass


class StatusWidget(Widget):
    text = Property("aca va algo")
    statusCode = Property("Funciona OK")

class SocketStatusWidget(Widget):
    connected = BooleanProperty(False)
    
    
    def __init__(self, **kwargs):
        super(SocketStatusWidget, self).__init__(**kwargs)
        Clock.schedule_interval(self.update_status, 1)
        
            
        self.configberry = Configberry.Configberry()
        serverUrl = self.configberry.config.get("SERVIDOR","sio_host", fallback="")
        uuid = self.configberry.config.get("SERVIDOR","uuid")
        
        self.sioHandler = SioClientHandler(serverUrl, uuid)
        
        asyncio.run(self.sioHandler.start())
        

    def update_status(self, dt):
        # Replace this with your actual socket IO connection status check
        self.connected = self.sioHandler.connected

class MainApp(App):
    
    def __init__(self, **kwargs):
        super(MainApp, self).__init__(**kwargs)
        self.title = "Fiscalberry UI App"
    
    def build(self):
        return LayoutWidget()
