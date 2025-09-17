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

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.version import VERSION

logger = getLogger("GUI.App")

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
        logger.info("Inicializando FiscalberryApp...")
        super().__init__(**kwargs)
        
        try:
            self.message_queue = queue.Queue()  # Inicializar la variable message_queue aquí
            logger.debug("Cola de mensajes inicializada")
            
            self._service_controller = ServiceController()
            logger.debug("ServiceController inicializado")
            
            self._configberry = Configberry()
            logger.debug("Configberry inicializado")
            
            self._stopping = False  # Bandera para evitar múltiples llamadas de cierre
            logger.debug("Variables de control inicializadas")

            self.updatePropertiesWithConfig()
            logger.info("Propiedades de configuración actualizadas")
            
            # Programar la verificación del estado de SocketIO cada 2 segundos
            Clock.schedule_interval(self._check_sio_status, 2)
            Clock.schedule_interval(self._check_rabbit_status, 2)
            logger.debug("Schedulers de verificación de estado configurados")

            # Configurar manejadores de señales para Windows
            self._setup_signal_handlers()
            logger.debug("Manejadores de señales configurados")
            
            logger.info("FiscalberryApp inicializada exitosamente")
        except Exception as e:
            logger.error(f"Error durante inicialización de FiscalberryApp: {e}", exc_info=True)
            raise
        
    def updatePropertiesWithConfig(self):
        """
        Actualiza las propiedades de la aplicación con los valores de configuración.
        """
        try:
            logger.debug("Actualizando propiedades con configuración...")
            self.uuid = self._configberry.get("SERVIDOR", "uuid", fallback="")
            self.host = self._configberry.get("SERVIDOR", "sio_host", fallback="")
            self.tenant = self._configberry.get("Paxaprinter", "tenant", fallback="")
            self.siteName = self._configberry.get("Paxaprinter", "site_name", fallback="")
            self.siteAlias = self._configberry.get("Paxaprinter", "alias", fallback="")
            
            logger.info(f"Configuración cargada - UUID: {self.uuid[:8]}..., Host: {self.host}, Tenant: {self.tenant}")
            logger.debug(f"Site Name: {self.siteName}, Site Alias: {self.siteAlias}")
        except Exception as e:
            logger.error(f"Error al actualizar propiedades con configuración: {e}", exc_info=True)
            # Establecer valores por defecto en caso de error
            self.uuid = ""
            self.host = ""
            self.tenant = ""
            self.siteName = ""
            self.siteAlias = ""

    def _check_sio_status(self, dt):
        """Verifica el estado de la conexión SocketIO y actualiza la propiedad."""
        try:
            previous_status = self.sioConnected
            self.sioConnected = self._service_controller.isSocketIORunning()
            
            # Log solo cuando cambia el estado para evitar spam
            if previous_status != self.sioConnected:
                if self.sioConnected:
                    logger.info("SocketIO conectado exitosamente")
                else:
                    logger.warning("SocketIO desconectado")
                    
        except Exception as e:
            logger.error(f"Error al verificar estado de SocketIO: {e}")
            self.sioConnected = False
            
    def _check_rabbit_status(self, dt):
        """Verifica el estado de la conexión RabbitMQ y actualiza la propiedad."""
        try:
            previous_status = self.rabbitMqConnected
            self.rabbitMqConnected = self._service_controller.isRabbitRunning()
            
            # Log solo cuando cambia el estado para evitar spam
            if previous_status != self.rabbitMqConnected:
                if self.rabbitMqConnected:
                    logger.info("RabbitMQ conectado exitosamente")
                else:
                    logger.warning("RabbitMQ desconectado")
                    
        except Exception as e:
            logger.error(f"Error al verificar estado de RabbitMQ: {e}")
            self.rabbitMqConnected = False
    
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
            current_screen = sm.current
            
            if self.tenant and self.tenant.strip():
                # Si hay un tenant, ir a la pantalla principal (solo si no estamos ya ahí)
                if current_screen != "main" and sm.has_screen("main"):
                    sm.current = "main"
                elif not sm.has_screen("main"):
                    print("Advertencia: No se encontró la pantalla 'main'.")
            else:
                # Si no hay tenant, ir a la pantalla de adopción (solo si no estamos ya ahí)
                if current_screen != "adopt" and sm.has_screen("adopt"):
                    sm.current = "adopt"
                    self.on_stop_service() # Detener servicio si se des-adopta
                elif not sm.has_screen("adopt"):
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

        try:
            # Usar el método específico para GUI que no causa problemas de cierre
            if hasattr(self._service_controller, 'stop_for_gui'):
                self._service_controller.stop_for_gui()
            else:
                # Fallback al método más seguro
                self._service_controller._stop_services_only()
            print("Servicios detenidos desde la GUI")
        except Exception as e:
            print(f"Error al detener servicios desde GUI: {e}")
    
    def restart_service(self):
        """Reiniciar el servicio completamente."""
        print("Reiniciando servicio...")
        
        def do_restart():
            try:
                # Primero detener el servicio
                if hasattr(self._service_controller, 'stop_for_gui'):
                    self._service_controller.stop_for_gui()
                else:
                    self._service_controller._stop_services_only()
                
                # Esperar un momento para que se detengan completamente
                time.sleep(2)
                
                # Luego iniciarlo de nuevo
                self._service_controller.start()
                print("Servicio reiniciado correctamente")
                
            except Exception as e:
                print(f"Error al reiniciar servicio: {e}")
        
        # Ejecutar en un hilo separado para no bloquear la UI
        Thread(target=do_restart, daemon=True).start()
    
    
    def on_stop(self):
        """Este método se llama al cerrar la aplicación."""
        if self._stopping:
            return

        print("Cerrando aplicación inmediatamente...")
        self._stopping = True

        # NO esperar a los servicios - cerrar inmediatamente
        try:
            # Detener los schedulers de Kivy inmediatamente
            Clock.unschedule(self._check_sio_status)
            Clock.unschedule(self._check_rabbit_status)
        except:
            pass

        # Forzar cierre inmediato sin esperar servicios
        print("Forzando cierre inmediato...")
        Clock.schedule_once(self._immediate_force_exit, 0.1)
        return False  # No dejar que Kivy maneje el cierre
    
    def _immediate_force_exit(self, dt):
        """Forzar salida inmediata sin esperar servicios."""
        try:
            # Intentar parar servicios rápidamente en background
            def stop_services_background():
                try:
                    self._service_controller._stop_event.set()
                    if hasattr(self._service_controller, 'sio') and self._service_controller.sio:
                        self._service_controller.sio.stop()
                except:
                    pass

            # Ejecutar en background sin bloquear
            thread = threading.Thread(target=stop_services_background, daemon=True)
            thread.start()
        except:
            pass

        # Salir inmediatamente
        try:
            print("Terminando proceso...")
            os._exit(0)
        except:
            pass
    
    def _setup_signal_handlers(self):
        """Configurar manejadores de señales para cierre limpio."""
        try:
            def signal_handler(signum, frame):
                print(f"Señal {signum} recibida, saliendo inmediatamente...")
                os._exit(0)

            # Registrar manejadores para las señales comunes
            signal.signal(signal.SIGINT, signal_handler)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, signal_handler)
            if hasattr(signal, 'SIGBREAK'):  # Windows
                signal.signal(signal.SIGBREAK, signal_handler)

        except Exception as e:
            print(f"Error configurando manejadores de señales: {e}")
    
    def _on_window_close(self, *args):
        """Maneja el cierre de la ventana de forma inmediata"""
        print("Ventana cerrada por el usuario, saliendo...")
        self._immediate_force_exit_standalone()
        return True

    def _immediate_force_exit_standalone(self):
        """Sale inmediatamente sin esperar procesos"""
        try:
            os._exit(0)  # Salida inmediata sin cleanup
        except Exception:
            sys.exit(1)
        
        
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

        # Configurar el cierre de ventana para Windows
        try:
            from kivy.core.window import Window
            Window.bind(on_request_close=self._on_window_close)
        except:
            pass

        # Verificar ya tiene tenant o debe ser adoptado
        if self.tenant and self.tenant.strip():
            # Si hay un tenant válido, ir directamente a la pantalla principal
            sm.current = "main"
        else:
            # Si no hay tenant, mostrar la pantalla de adoptar
            sm.current = "adopt"

        return sm

if __name__ == "__main__":
    FiscalberryApp().run()