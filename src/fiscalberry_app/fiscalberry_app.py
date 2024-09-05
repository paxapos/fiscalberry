import os
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty
from jnius import autoclass
from common.Configberry import Configberry
from twisted.internet.protocol import Protocol, ClientFactory
from twisted.internet import reactor

# Importo el módulo que se encarga de la comunicación con el servidor
from common.Configberry import Configberry
from common.fiscalberry_logger import getLogger

logger = getLogger()

SERVICE_NAME = u'{packagename}.Service{servicename}'.format(
    packagename=u'com.paxapos.fiscalberry',
    servicename=u'Fiscalberryservice'
)


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

    connected: bool = BooleanProperty(False)
    
    fiscalberry_sio = None
    
    sio = None

    def __init__(self, **kwargs):
        super(FiscalberryApp, self).__init__(**kwargs)
       
        # load APP config
        serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
        self.sioServerUrl = serverUrl if serverUrl else self.sioServerUrl

        # Crear la fábrica del cliente y conectar al socket
        factory = AppInterConFactory(self)
        reactor.connectUNIX("/data/data/com.paxapos.fiscalberry/files/fiscalberry_socket", factory)

    def start_service(self, finishing=False):
        service = autoclass(SERVICE_NAME)
        mActivity = autoclass(u'org.kivy.android.PythonActivity').mActivity
        argument = ''
        if finishing:
            argument = '{"stop_service": 1}'
        service.start(mActivity, argument)
        if finishing:
            self.service = None
        else:
            self.service = service

        self.connected = True

    def stop_service(self):
        service = autoclass(SERVICE_NAME)
        mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
        service.stop(mActivity)
        self.start_service(finishing=True)
        self.connected = False

    def start_fiscaberry_service():
        service = autoclass('com.paxapos.fiscalberry.ServiceFiscalberryservice')
        mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
        argument = ''
        service.start(mActivity, argument)
        
    def build(self):
        self.root = MainLayout()
        self.log_widget = self.root.log_widget
        return self.root

    def add_log(self, text):
        self.log_widget.add_log(text)
        

    def store_new_host(self, value):
        host = value
        logger.info(f"FiscalberryApp: vino para guardar sio_host:: {host} antes estaba {self.sioServerUrl}")
        if host != self.sioServerUrl:
            logger.info(f"FiscalberryApp: se guarda nuevo sio_host:: {host}")
            configberry.writeKeyForSection("SERVIDOR", "sio_host", host)


    def on_resume(self):
        if self.service:
            self.start_service()
    
    def on_start(self):
        """
        This function is executed when the application starts.
        It is a Kivy function.
        """

        # Iniciar con el ícono rojo por defecto
        self.start_service()
        logger.info("FiscalberryApp: Iniciando la aplicación")
        
        
    def on_stop(self):
        """
        This function is executed when the application is closed.
        It is a Kivy function.
        """
        self.stop_service()
        logger.info("FiscalberryApp: Deteniendo la aplicación")
    
    
