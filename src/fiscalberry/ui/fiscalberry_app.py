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
from kivy.properties import StringProperty, BooleanProperty
from fiscalberry.ui.log_screen import LogScreen
from threading import Thread
import time
import sys
import os
import signal


from fiscalberry.version import VERSION

class FiscalberryApp(App):
    name = StringProperty("Servidor de Impresión")
    uuid = StringProperty("")
    host = StringProperty("")
    tenant = StringProperty("")
    siteName = StringProperty("")
    siteAlias = StringProperty("")
    version = StringProperty( VERSION )

    
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
        self.message_queue = queue.Queue()  # Inicializar la variable message_queue aquí
        
        self._service_controller = ServiceController()
        self._configberry = Configberry()
        self._stopping = False  # Bandera para evitar múltiples llamadas de cierre

        self.updatePropertiesWithConfig()
        
        # Programar la verificación del estado de SocketIO cada 2 segundos
        Clock.schedule_interval(self._check_sio_status, 2)
        Clock.schedule_interval(self._check_rabbit_status, 2)
        
    def updatePropertiesWithConfig(self):
        """
        Actualiza las propiedades de la aplicación con los valores de configuración.
        """
        self.uuid = self._configberry.get("SERVIDOR", "uuid", fallback="")
        self.host = self._configberry.get("SERVIDOR", "sio_host", fallback="")
        self.tenant = self._configberry.get("Paxaprinter", "tenant", fallback="")
        self.siteName = self._configberry.get("Paxaprinter", "site_name", fallback="")
        self.siteAlias = self._configberry.get("Paxaprinter", "alias", fallback="")

    def _check_sio_status(self, dt):
        """Verifica el estado de la conexión SocketIO y actualiza la propiedad."""
        self.sioConnected = self._service_controller.isSocketIORunning()
        # Opcionalmente, puedes actualizar el status_message aquí también si lo deseas
        # if self.sioConnected:
        #     self.status_message = "Conectado a SocketIO"
        # else:
        #     self.status_message = "Esperando conexión SocketIO..."
            
    def _check_rabbit_status(self, dt):
        """Verifica el estado de la conexión RabbitMQ y actualiza la propiedad."""
        self.rabbitMqConnected = self._service_controller.isRabbitRunning()
        # Opcionalmente, puedes actualizar el status_message aquí también si lo deseas
        # if self.rabbitMqConnected:
        #     self.status_message = "Conectado a RabbitMQ"
        # else:
        #     self.status_message = "Esperando conexión RabbitMQ..."
    
    @mainthread  # Decorar el método
    def _on_config_change(self, data):
        """
        Callback que se llama cuando hay un cambio en la configuración.
        hay que renderizar las pantallas de nuevo para que se vean los cambios.
        """

        self.updatePropertiesWithConfig()
        
        

        # Usar el ScreenManager existente (self.root)
        sm = self.root
        if sm: # Verificar que self.root ya existe
            if self.tenant:
                # Si hay un tenant, ir a la pantalla principal
                if sm.has_screen("main"):
                    sm.current = "main"
                else:
                    print("Advertencia: No se encontró la pantalla 'main'.")
            else:
                # Si no hay tenant, ir a la pantalla de adopción
                if sm.has_screen("adopt"):
                    sm.current = "adopt"
                    self.on_stop_service() # Detener servicio si se des-adopta

                else:
                    print("Advertencia: No se encontró la pantalla 'adopt'.")
        else:
            print("Error: self.root (ScreenManager) aún no está disponible.")
        

    def on_toggle_service(self):
        """Llamado desde la GUI para alternar el estado del servicio."""
        if self._service_controller.is_service_running():
            # Si el servicio está corriendo, detenerlo
            self.on_stop_service()
        else:
            # Si el servicio no está corriendo, iniciarlo
            self.on_start_service()
        

    def on_start_service(self):
        """Llamado desde la GUI para iniciar el servicio."""
        Thread(target=self._service_controller.start, daemon=True).start()


    def on_stop_service(self):
        """Llamado desde la GUI para detener el servicio."""
        # Evitar múltiples llamadas
        if self._stopping:
            return
        
        print("Deteniendo servicios desde la GUI...")
        
        # Solo detener los servicios, no forzar salida de la aplicación
        self._service_controller._stop_services_only()
        print("Servicios detenidos desde la GUI")
    
    
    def on_stop(self):
        # Este método se llama al cerrar la aplicación
        if self._stopping:
            return
        
        print("Cerrando aplicación, deteniendo servicios...")
        self._stopping = True
        
        # Solo detener los servicios, no llamar a app.stop() para evitar recursión
        self._service_controller._stop_services_only()
        print("Servicios detenidos...")
        
        # Usar múltiples estrategias para forzar la salida
        Clock.schedule_once(self._force_exit, 0.1)
    
    def _force_exit(self, dt):
        """Método auxiliar para forzar la salida después de la limpieza."""
        import signal
        import threading
        
        print("Forzando salida de la aplicación...")
        
        # Estrategia 1: Detener el Clock de Kivy
        try:
            Clock.stop()
        except:
            pass
        
        # Estrategia 2: Terminar threads activos
        try:
            for thread in threading.enumerate():
                if thread != threading.current_thread() and thread.is_alive():
                    if hasattr(thread, '_stop'):
                        thread._stop()
        except:
            pass
        
        # Estrategia 3: Usar signal para terminar el proceso
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except:
            pass
        
        # Estrategia 4: Exit forzado como último recurso
        os._exit(0)
        
        
    def build(self):
        self.title = "Servidor de Impresión"
        
        self.icon = os.path.join(os.path.dirname(__file__), "assets", "fiscalberry.png")
        
        # escuchar cambios en configberry
        self._configberry.add_listener(self._on_config_change)

        self.on_start_service()

        # Cargar el archivo KV
        kv_path = os.path.join(os.path.dirname(__file__), "kv", "main.kv")
        Builder.load_file(kv_path)

        sm = ScreenManager()
        #login_screen = LoginScreen(name="login")
        #sm.add_widget(login_screen)
        sm.add_widget(AdoptScreen(name="adopt"))
        sm.add_widget(MainScreen(name="main"))

        # Agregar la pantalla de logs
        log_screen = LogScreen(name="logs")
        sm.add_widget(log_screen)

        # Verificar ya tiene tenant o debe ser adoptado
        if self.tenant:
            # Si hay un tenant, ir directamente a la pantalla principal
            sm.current = "main"
        else:
            # Si no hay token, mostrar la pantalla de adoptar
            sm.current = "adopt"

        return sm

if __name__ == "__main__":
    FiscalberryApp().run()