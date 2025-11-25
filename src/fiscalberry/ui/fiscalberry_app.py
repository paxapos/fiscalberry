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
    queueCount = NumericProperty(0)
    lastPrintTime = StringProperty("") 
    printLocation = StringProperty("") 
    
    assetpath = os.path.join(os.path.dirname(__file__), "assets")
    
    # Configurar el icono de la aplicación para la barra de tareas
    icon = os.path.join(assetpath, "fiscalberry.ico")
    
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
            # Detectar si estamos en Android
            self._is_android = self._detect_android()
            if self._is_android:
                logger.info("✓ Ejecutando en Android")
                # Solicitar permisos necesarios
                self._request_android_permissions()
            
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
            
            # Programar verificación de estado menos frecuente para mejor performance
            Clock.schedule_interval(self._check_sio_status, 5)  # Reducido de 2 a 5 segundos
            Clock.schedule_interval(self._check_rabbit_status, 5)  # Reducido de 2 a 5 segundos
            logger.debug("Schedulers de verificación de estado configurados (optimizado)")

            # Configurar manejadores de señales (solo en escritorio)
            if not self._is_android:
                self._setup_signal_handlers()
                logger.debug("Manejadores de señales configurados")
            
            # Iniciar servicio Android si corresponde
            if self._is_android:
                self._start_android_service()
            
            logger.info("FiscalberryApp inicializada exitosamente")
        except Exception as e:
            logger.error(f"Error durante inicialización de FiscalberryApp: {e}", exc_info=True)
            raise
    
    def _detect_android(self):
        """Detecta si la app está corriendo en Android"""
        try:
            from jnius import autoclass
            return True
        except ImportError:
            return False
    
    def _request_android_permissions(self):
        """Solicita todos los permisos necesarios en Android"""
        try:
            from fiscalberry.common.android_permissions import (
                request_all_permissions, 
                get_permissions_status_summary,
                request_storage_permissions,
                request_network_permissions
            )
            
            logger.info("Solicitando permisos de Android...")
            
            # Solicitar permisos críticos primero
            request_storage_permissions()
            request_network_permissions()
            
            # Luego solicitar el resto
            request_all_permissions()
            
            # Mostrar resumen
            status = get_permissions_status_summary()
            logger.info(f"\n{status}")
            
        except Exception as e:
            logger.error(f"Error solicitando permisos Android: {e}", exc_info=True)
    
    def _start_android_service(self):
        """Inicia el servicio Android en segundo plano"""
        try:
            from android import AndroidService
            
            logger.info("Iniciando servicio Android...")
            service = AndroidService('Fiscalberry Service', 'running')
            service.start('Fiscalberry iniciado')
            logger.info("✓ Servicio Android iniciado")
            
        except ImportError:
            logger.warning("AndroidService no disponible - usando método alternativo")
            try:
                from jnius import autoclass
                
                PythonService = autoclass('org.kivy.android.PythonService')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                
                activity = PythonActivity.mActivity
                PythonService.start(activity, '')
                logger.info("✓ Servicio Android iniciado (método alternativo)")
                
            except Exception as e:
                logger.error(f"No se pudo iniciar servicio Android: {e}")
                logger.warning("La app funcionará solo cuando esté en primer plano")
        except Exception as e:
            logger.error(f"Error iniciando servicio Android: {e}", exc_info=True)
    
    def build(self):
        """Construye la aplicación de forma optimizada."""
        logger.info("Construyendo interfaz de usuario...")
        
        # Configurar título y icono
        self.title = "Servidor de Impresión"
        
        # Configurar el icono de la ventana de forma optimizada
        try:
            icon_path = os.path.join(self.assetpath, "fiscalberry.ico")
            if os.path.exists(icon_path):
                self.icon = icon_path
                logger.info(f"Icono configurado: {icon_path}")
                
                # Configuración específica para Windows
                if sys.platform == 'win32':
                    self._set_windows_icon(icon_path)
            else:
                # Fallback a PNG si ICO no existe
                png_icon = os.path.join(self.assetpath, "fiscalberry.png")
                if os.path.exists(png_icon):
                    self.icon = png_icon
                    logger.info(f"Usando icono PNG fallback: {png_icon}")
        except Exception as e:
            logger.error(f"Error configurando icono: {e}")
        
        # Cargar el archivo KV de forma optimizada
        try:
            kv_path = os.path.join(os.path.dirname(__file__), "kv", "main.kv")
            if os.path.exists(kv_path):
                Builder.load_file(kv_path)
                logger.debug("Archivo KV cargado")
        except Exception as e:
            logger.error(f"Error cargando archivo KV: {e}")
        
        # Escuchar cambios en configberry
        self._configberry.add_listener(self._on_config_change)
        
        # Crear el ScreenManager y las pantallas de forma optimizada
        sm = ScreenManager()
        
        # Agregar pantallas en orden de uso más probable
        sm.add_widget(AdoptScreen(name='adopt'))
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(LogScreen(name='logs'))  # Consistencia en naming
        
        # Configurar el cierre de ventana para Windows
        try:
            from kivy.core.window import Window
            Window.bind(on_request_close=self._on_window_close)
        except Exception as e:
            logger.debug(f"No se pudo configurar cierre de ventana: {e}")
        
        # Determinar pantalla inicial basada en configuración
        if self.tenant and self.tenant.strip():
            sm.current = 'main'
            logger.info("Iniciando en pantalla principal (tenant configurado)")
            # Iniciar servicios automáticamente si hay tenant
            self.on_start_service()
        else:
            sm.current = 'adopt'
            logger.info("Iniciando en pantalla de adopción (tenant no configurado)")
        
        return sm
    
    def _set_windows_icon(self, icon_path):
        """Configura el icono específicamente para Windows."""
        try:
            import platform
            if platform.system() == 'Windows':
                # Intentar configurar el icono usando kivy
                from kivy.core.window import Window
                Window.set_icon(icon_path)
                logger.debug("Icono de ventana configurado con Kivy")
                
                # Para el icono de la barra de tareas en Windows
                try:
                    import ctypes
                    from ctypes import wintypes
                    
                    # Obtener el handle de la ventana
                    hwnd = ctypes.windll.user32.GetActiveWindow()
                    if hwnd:
                        # Cargar el icono
                        hicon = ctypes.windll.user32.LoadImageW(
                            None, icon_path, 1, 0, 0, 0x00000010 | 0x00008000
                        )
                        if hicon:
                            # Configurar icono pequeño y grande
                            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon)  # WM_SETICON, ICON_SMALL
                            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon)  # WM_SETICON, ICON_BIG
                            logger.debug("Icono de barra de tareas configurado")
                except Exception as e:
                    logger.debug(f"No se pudo configurar icono de barra de tareas: {e}")
                    
        except Exception as e:
            logger.error(f"Error configurando icono de Windows: {e}")
    
    def on_start(self):
        """Se ejecuta después de que la aplicación inicie."""
        logger.info("Aplicación iniciada, configurando icono final...")
        
        # Configurar el icono después de que la ventana esté completamente creada
        try:
            icon_path = os.path.join(self.assetpath, "fiscalberry.ico")
            if os.path.exists(icon_path) and sys.platform == 'win32':
                # Esperar un poco para que la ventana esté completamente inicializada
                Clock.schedule_once(lambda dt: self._set_windows_icon_delayed(icon_path), 1)
        except Exception as e:
            logger.error(f"Error en on_start configurando icono: {e}")
    
    def _set_windows_icon_delayed(self, icon_path):
        """Configura el icono de Windows con un retraso para asegurar que la ventana esté lista."""
        try:
            if sys.platform == 'win32':
                import ctypes
                from ctypes import wintypes
                
                # Buscar la ventana de Fiscalberry
                def enum_windows_proc(hwnd, lParam):
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
                        if "Servidor de Impresión" in buffer.value or "Fiscalberry" in buffer.value:
                            # Cargar y configurar el icono
                            hicon = ctypes.windll.user32.LoadImageW(
                                None, icon_path, 1, 0, 0, 0x00000010 | 0x00008000
                            )
                            if hicon:
                                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon)  # ICON_SMALL
                                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon)  # ICON_BIG
                                logger.info("Icono de barra de tareas configurado exitosamente")
                            return False  # Detener enumeración
                    return True
                
                # Enumerar ventanas para encontrar la nuestra
                enum_windows_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                ctypes.windll.user32.EnumWindows(enum_windows_proc_type(enum_windows_proc), 0)
                
        except Exception as e:
            logger.error(f"Error configurando icono de barra de tareas: {e}")
        
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
        """Verifica el estado de la conexión SocketIO de forma optimizada."""
        try:
            previous_status = self.sioConnected
            # Check más eficiente sin llamadas costosas innecesarias
            new_status = self._service_controller.isSocketIORunning()
            
            if previous_status != new_status:
                self.sioConnected = new_status
                if new_status:
                    logger.info("SocketIO conectado")
                    self.status_message = "Conectado - Listo para imprimir"
                else:
                    logger.warning("SocketIO desconectado")
                    self.status_message = "Desconectado - Verificando conexión..."
                    
        except Exception as e:
            # Manejo de errores silencioso para evitar spam en logs
            if self.sioConnected:  # Solo log si cambia de conectado a error
                logger.error(f"Error verificando SocketIO: {e}")
            self.sioConnected = False
            self.status_message = "Error de conexión"
            
    def _check_rabbit_status(self, dt):
        """Verifica el estado de la conexión RabbitMQ de forma optimizada.""" 
        try:
            previous_status = self.rabbitMqConnected
            new_status = self._service_controller.isRabbitRunning()
            
            if previous_status != new_status:
                self.rabbitMqConnected = new_status
                if new_status:
                    logger.info("RabbitMQ conectado")
                else:
                    logger.warning("RabbitMQ desconectado")
                    
        except Exception as e:
            # Manejo de errores silencioso para evitar spam en logs
            if self.rabbitMqConnected:  # Solo log si cambia de conectado a error
                logger.error(f"Error verificando RabbitMQ: {e}")
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
        """Llamado desde la GUI para iniciar el servicio de forma optimizada."""
        if not self._service_controller.is_service_running():
            logger.info("Iniciando servicios desde GUI...")
            self.status_message = "Iniciando servicios..."
            Thread(target=self._service_controller.start, daemon=True).start()
        else:
            logger.debug("Servicio ya en ejecución, omitiendo inicio")


    def on_stop_service(self):
        """Llamado desde la GUI para detener el servicio de forma optimizada."""
        # Evitar múltiples llamadas
        if self._stopping:
            return
        
        logger.info("Deteniendo servicios desde GUI...")
        self.status_message = "Deteniendo servicios..."

        try:
            # Usar el método específico para GUI que no causa problemas de cierre
            if hasattr(self._service_controller, 'stop_for_gui'):
                self._service_controller.stop_for_gui()
            else:
                # Fallback al método más seguro
                self._service_controller._stop_services_only()
            
            self.status_message = "Servicios detenidos"
            logger.info("Servicios detenidos desde GUI")
        except Exception as e:
            logger.error(f"Error al detener servicios desde GUI: {e}")
            self.status_message = "Error deteniendo servicios"
    
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
        
        


if __name__ == "__main__":
    FiscalberryApp().run()