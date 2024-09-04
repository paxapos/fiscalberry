import os
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty

from dotenv import load_dotenv
from common.Configberry import Configberry

# Importo el módulo que se encarga de la comunicación con el servidor
from fiscalberry_sio import FiscalberrySio
from common.discover import send_discover_in_thread
from common.Configberry import Configberry

from common.fiscalberry_logger import getLogger
logger = getLogger()
    
    
load_dotenv()


configberry = Configberry()
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
    assetpath = os.path.dirname(os.path.abspath(__file__))
    
    background_image = StringProperty(f"{assetpath}/assets/bg.jpg")
    logo_image = StringProperty(f"{assetpath}/assets/fiscalberry.png")
    disconnected_image = StringProperty(f"{assetpath}/assets/disconnected.png")
    connected_image = StringProperty(f"{assetpath}/assets/connected.png")

    sioServerUrl = os.environ.get("SIO_SERVER_URL")

    connected: bool = BooleanProperty(False)
    
    fiscalberry_sio = None
    
    sio = None

    def __init__(self, **kwargs):
        super(FiscalberryApp, self).__init__(**kwargs)
        
        self.sio = self.__socketio_client()
       

        # load APP config
        serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
        self.uuid = configberry.config.get("SERVIDOR", "uuid")
        self.uuidSmall = self.uuid[:8]

        self.sioServerUrl = serverUrl if serverUrl else self.sioServerUrl


    def __socketio_client(self):
        configberry = Configberry()

        logger.info("Preparando Fiscalberry Server")

        serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
        uuid = configberry.config.get("SERVIDOR", "uuid")
        send_discover_in_thread()
        self.fiscalberry_sio = FiscalberrySio(serverUrl, uuid)
        
        sio = self.fiscalberry_sio.sio
        
        @sio.on("connect", namespace='/paxaprinter')
        def on_connect():
            # change connected property
            self.connected = True
            
        @sio.on('disconnect', namespace='/paxaprinter')
        def on_disconnect():
            self.connected = False

        
        self.fiscalberry_sio.start_only_status_in_thread()
            
        return sio   
            
        
    def build(self):
        self.root = MainLayout()
        self.log_widget = self.root.log_widget
        return self.root

    def add_log(self, text):
        self.log_widget.add_log(text)

    def store_new_host(self, value):
        host = value
        logger.info(f"FiscalberryApp: vino para guardar sio_host:: {
                    host} antes estaba {self.sioServerUrl}")
        if host != self.sioServerUrl:
            logger.info(f"FiscalberryApp: se guarda nuevo sio_host:: {host}")
            configberry.writeKeyForSection("SERVIDOR", "sio_host", host)

    
    def on_start(self):
        """
        This function is executed when the application starts.
        It is a Kivy function.
        """

        # Iniciar con el ícono rojo por defecto
        logger.info("FiscalberryApp: Iniciando la aplicación")
        
        
    def on_stop(self):
        """
        This function is executed when the application is closed.
        It is a Kivy function.
        """
        if self.fiscalberry_sio:
            self.fiscalberry_sio.stop()
            logger.info("FiscalberryApp: Deteniendo la aplicación")
    
    