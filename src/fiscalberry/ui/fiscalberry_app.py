from kivy.app import App
from kivy.uix.screenmanager import ScreenManager
from fiscalberry.ui.main_screen import MainScreen
from fiscalberry.ui.login_screen import LoginScreen
from fiscalberry.ui.adopt_screen import AdoptScreen
from kivy.clock import Clock, mainthread
import threading
import queue
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.service_controller import ServiceController
from kivy.lang import Builder
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from fiscalberry.ui.log_screen import LogScreen
from threading import Thread
import time
import sys
import os
import signal
from fiscalberry.version import VERSION
from kivy.metrics import dp
from kivy.core.window import Window

class FiscalberryApp(App):
    name = StringProperty("Servidor de Impresión")
    uuid = StringProperty("")
    host = StringProperty("")
    tenant = StringProperty("")
    siteName = StringProperty("")
    siteAlias = StringProperty("")
    printLocation = StringProperty("")
    lastPrintTime = StringProperty("")
    queueCount = NumericProperty(0)
    version = StringProperty(VERSION)
    
    assetpath = os.path.join(os.path.dirname(__file__), "assets")
    background_image = StringProperty(os.path.join(assetpath, "bg.jpg"))
    logo_image = StringProperty(os.path.join(assetpath, "fiscalberry.png"))
    disconnected_image = StringProperty(os.path.join(assetpath, "disconnected.png"))
    connected_image = StringProperty(os.path.join(assetpath, "connected.png"))
    
    sioConnected: bool = BooleanProperty(False)
    rabbitMqConnected: bool = BooleanProperty(False)
    status_message = StringProperty("Esperando conexión...")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.message_queue = queue.Queue()
        self._service_controller = ServiceController()
        self._configberry = Configberry()
        self._stopping = False
        
        # Detectar plataforma y ajustar UI
        self._setup_window_size()
        
        self.updatePropertiesWithConfig()
        
        # Programar verificaciones de estado
        Clock.schedule_interval(self._check_sio_status, 2)
        Clock.schedule_interval(self._check_rabbit_status, 2)
        Clock.schedule_interval(self._update_print_info, 5)
        
        # Verificar parámetros de vinculación automática
        self._check_auto_adoption()
    
    def _setup_window_size(self):
        """Ajusta el tamaño de ventana según la plataforma"""
        try:
            from kivy.utils import platform
            if platform == 'android':
                # En Android, usar tamaños relativos con dp()
                Window.size = (Window.width, Window.height)
            else:
                # En escritorio, establecer un tamaño razonable
                Window.size = (400, 700)
        except:
            pass
    
    def _check_auto_adoption(self):
        """Verifica si hay parámetros de vinculación automática en la URL o almacenamiento"""
        try:
            from kivy.utils import platform
            if platform == 'android':
                # Intentar obtener el intent que lanzó la app
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                activity = PythonActivity.mActivity
                intent = activity.getIntent()
                
                if intent:
                    # Verificar si hay datos en el intent
                    data = intent.getData()
                    if data:
                        # Extraer parámetros de autenticación de la URL
                        url_string = data.toString()
                        self._process_adoption_url(url_string)
        except Exception as e:
            print(f"Error checking auto adoption: {e}")
    
    def _process_adoption_url(self, url):
        """Procesa una URL de adopción y vincula automáticamente"""
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            
            # Buscar token o credenciales en los parámetros
            if 'token' in params:
                token = params['token'][0]
                self._save_token_and_link(token)
            elif 'tenant' in params:
                # Guardar tenant directamente
                tenant = params['tenant'][0]
                self._configberry.writeKeyForSection("Paxaprinter", "tenant", tenant)
                if 'site_name' in params:
                    self._configberry.writeKeyForSection("Paxaprinter", "site_name", params['site_name'][0])
                if 'alias' in params:
                    self._configberry.writeKeyForSection("Paxaprinter", "alias", params['alias'][0])
                
                self.updatePropertiesWithConfig()
                
                # Notificar cambio
                Clock.schedule_once(lambda dt: self._on_config_change({}), 0.5)
        except Exception as e:
            print(f"Error processing adoption URL: {e}")
    
    def _save_token_and_link(self, token):
        """Guarda el token y vincula el dispositivo"""
        try:
            from fiscalberry.common.token_manager import save_token
            if save_token(token):
                print("Token guardado exitosamente")
                # Actualizar configuración
                self.updatePropertiesWithConfig()
                Clock.schedule_once(lambda dt: self._on_config_change({}), 0.5)
        except Exception as e:
            print(f"Error saving token: {e}")
    
    def updatePropertiesWithConfig(self):
        """Actualiza las propiedades de la aplicación con los valores de configuración"""
        self.uuid = self._configberry.get("SERVIDOR", "uuid", fallback="")
        self.host = self._configberry.get("SERVIDOR", "sio_host", fallback="")
        self.tenant = self._configberry.get("Paxaprinter", "tenant", fallback="")
        self.siteName = self._configberry.get("Paxaprinter", "site_name", fallback="")
        self.siteAlias = self._configberry.get("Paxaprinter", "alias", fallback="")
        self.printLocation = self._configberry.get("Paxaprinter", "print_location", fallback="")
    
    def _check_sio_status(self, dt):
        """Verifica el estado de la conexión SocketIO"""
        self.sioConnected = self._service_controller.isSocketIORunning()
    
    def _check_rabbit_status(self, dt):
        """Verifica el estado de la conexión RabbitMQ"""
        self.rabbitMqConnected = self._service_controller.isRabbitRunning()
    
    def _update_print_info(self, dt):
        """Actualiza información de impresiones"""
        try:
            # Aquí deberías obtener la info real del servicio
            # Por ahora, placeholder
            self.queueCount = 0  # Obtener del servicio
            # self.lastPrintTime se actualizaría cuando haya una impresión
        except Exception as e:
            print(f"Error updating print info: {e}")
    
    @mainthread
    def _on_config_change(self, data):
        """Callback cuando hay cambios en la configuración"""
        self.updatePropertiesWithConfig()
        
        sm = self.root
        if sm:
            if self.tenant:
                if sm.has_screen("main"):
                    sm.current = "main"
            else:
                if sm.has_screen("adopt"):
                    sm.current = "adopt"
                    self.on_stop_service()
    
    def on_toggle_service(self):
        """Alterna el estado del servicio"""
        if self._service_controller.is_service_running():
            self.on_stop_service()
        else:
            self.on_start_service()
    
    def on_start_service(self):
        """Inicia el servicio"""
        Thread(target=self._service_controller.start, daemon=True).start()
    
    def on_stop_service(self):
        """Detiene el servicio"""
        if self._stopping:
            return
        print("Deteniendo servicios desde la GUI...")
        self._service_controller._stop_services_only()
        print("Servicios detenidos desde la GUI")
    
    def on_stop(self):
        """Se llama al cerrar la aplicación"""
        if self._stopping:
            return
        print("Cerrando aplicación, deteniendo servicios...")
        self._stopping = True
        self._service_controller._stop_services_only()
        print("Servicios detenidos...")
        Clock.schedule_once(self._force_exit, 0.1)
    
    def _force_exit(self, dt):
        """Fuerza la salida de la aplicación"""
        import signal
        import threading
        print("Forzando salida de la aplicación...")
        
        try:
            Clock.stop()
        except:
            pass
        
        try:
            for thread in threading.enumerate():
                if thread != threading.current_thread() and thread.is_alive():
                    if hasattr(thread, '_stop'):
                        thread._stop()
        except:
            pass
        
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except:
            pass
        
        os._exit(0)
    
    def build(self):
        self.title = "Servidor de Impresión"
        self.icon = os.path.join(os.path.dirname(__file__), "assets", "fiscalberry.png")
        
        # Escuchar cambios en configberry
        self._configberry.add_listener(self._on_config_change)
        self.on_start_service()
        
        # Cargar el archivo KV
        kv_path = os.path.join(os.path.dirname(__file__), "kv", "main.kv")
        Builder.load_file(kv_path)
        
        sm = ScreenManager()
        sm.add_widget(AdoptScreen(name="adopt"))
        sm.add_widget(MainScreen(name="main"))
        sm.add_widget(LogScreen(name="logs"))
        
        # Verificar si tiene tenant o debe ser adoptado
        if self.tenant:
            sm.current = "main"
        else:
            sm.current = "adopt"
        
        return sm

if __name__ == "__main__":
    FiscalberryApp().run()