from kivy.app import App
from kivy.uix.screenmanager import ScreenManager
from ui.main_screen import MainScreen
from ui.login_screen import LoginScreen
from ui.adopt_screen import AdoptScreen
from kivy.clock import Clock, mainthread
import threading
from common.fiscalberry_sio import FiscalberrySio
import queue

from kivy.lang import Builder
from kivy.properties import StringProperty, BooleanProperty
from ui.log_screen import LogScreen
from common.service_controller import ServiceController

class FiscalberryApp(App):
    
    assetpath = "ui"
    
    background_image = StringProperty(f"{assetpath}/assets/bg.jpg")
    logo_image = StringProperty(f"{assetpath}/assets/fiscalberry.png")
    disconnected_image = StringProperty(f"{assetpath}/assets/disconnected.png")
    connected_image = StringProperty(f"{assetpath}/assets/connected.png")
    
    connected: bool = BooleanProperty(False)
    
    status_message = StringProperty("Esperando conexión...")
    
    message_queue = None
    sio = None  # Inicializar la variable sio aquí
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.serviceController = None  # Inicializar la variable sio aquí
        self.message_queue = queue.Queue()  # Inicializar la variable message_queue aquí
    
    @mainthread  # Decorar el método
    def _on_config_change(self, data):
        """
        Callback que se llama cuando hay un cambio en la configuración.
        hay que renderizar las pantallas de nuevo para que se vean los cambios.
        """
        tenant = data.get("Paxaprinter", {}).get("tenant")
        
            
        # Usar el ScreenManager existente (self.root)
        sm = self.root
        if sm: # Verificar que self.root ya existe
            if tenant:
                # Si hay un tenant, ir a la pantalla principal
                if sm.has_screen("main"):
                    sm.current = "main"
                else:
                    print("Advertencia: No se encontró la pantalla 'main'.")
            else:
                # Si no hay tenant, ir a la pantalla de adopción
                if sm.has_screen("adopt"):
                    sm.current = "adopt"
                else:
                    print("Advertencia: No se encontró la pantalla 'adopt'.")
        else:
            print("Error: self.root (ScreenManager) aún no está disponible.")
        

    
    def build(self):
        self.title = "Servidor de Impresión"
        self.icon = "ui/assets/fiscalberry.png"  # Ruta al icono personalizado


        # Cargar el archivo KV
        Builder.load_file("ui/kv/main.kv")
        
        sm = ScreenManager()
        #login_screen = LoginScreen(name="login")
        #sm.add_widget(login_screen)
        sm.add_widget(AdoptScreen(name="adopt"))
        sm.add_widget(MainScreen(name="main"))
        
        
        # Agregar la pantalla de logs
        log_screen = LogScreen(name="logs")
        sm.add_widget(log_screen)
        
        
        # Leer host/uuid de tu configuración
        from common.Configberry import Configberry
        cfg = Configberry()
        host = cfg.get("SERVIDOR","sio_host")
        uuid = cfg.get("SERVIDOR","uuid","")
        
        cfg.add_listener(self._on_config_change)



        # Verificar si ya existe un token JWT guardado
        configberry = Configberry()
        tenant = configberry.get("Paxaprinter", "tenant", fallback=None)
        if tenant:
            # Si hay un token, ir directamente a la pantalla principal
            sm.current = "main"
        else:
            # Si no hay token, mostrar la pantalla de login
            sm.current = "adopt"

        return sm
    

if __name__ == "__main__":
    FiscalberryApp().run()