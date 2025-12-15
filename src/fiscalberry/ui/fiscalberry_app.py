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
    
    # Configurar el icono de la aplicación para la barra de tareas (solo Desktop)
    icon = os.path.join(assetpath, "fiscalberry.ico")
    
    # UI Minimalista - Propiedades de imágenes como strings vacíos
    # Mantener las propiedades para compatibilidad con archivos KV
    # pero con valores vacíos para no mostrar imágenes ni cargar texturas
    background_image = StringProperty("")
    logo_image = StringProperty("")
    disconnected_image = StringProperty("")
    connected_image = StringProperty("")
    
    sioConnected: bool = BooleanProperty(False)
    rabbitMqConnected: bool = BooleanProperty(False)
    
    status_message = StringProperty("Esperando conexión...")
    
    def __init__(self, **kwargs):
        logger.info("Inicializando FiscalberryApp...")
        super().__init__(**kwargs)
        
        try:
            # Inicializar variables básicas primero
            self.message_queue = queue.Queue()
            self._stopping = False
            self._is_android = False
            logger.debug("Variables básicas inicializadas")
            
            # Detectar si estamos en Android de forma segura
            try:
                self._is_android = self._detect_android()
                logger.info(f"Detección de Android: {self._is_android}")
            except Exception as e:
                logger.warning(f"Error detectando Android: {e}")
                self._is_android = False
            
            # Solicitar permisos de Android de forma segura
            if self._is_android:
                logger.info("✓ Ejecutando en Android")
                try:
                    self._request_android_permissions()
                except Exception as e:
                    logger.error(f"Error solicitando permisos Android: {e}")
            
            # Inicializar controladores de forma segura
            try:
                self._service_controller = ServiceController()
                logger.debug("ServiceController inicializado")
            except Exception as e:
                logger.error(f"Error inicializando ServiceController: {e}")
                self._service_controller = None
            
            try:
                self._configberry = Configberry()
                logger.debug("Configberry inicializado")
            except Exception as e:
                logger.error(f"Error inicializando Configberry: {e}")
                self._configberry = None

            # Actualizar propiedades de configuración de forma segura
            try:
                self.updatePropertiesWithConfig()
                logger.info("Propiedades de configuración actualizadas")
            except Exception as e:
                logger.error(f"Error actualizando propiedades: {e}")
            
            # Programar verificación de estado de forma segura
            try:
                Clock.schedule_interval(self._check_sio_status, 5)
                Clock.schedule_interval(self._check_rabbit_status, 5)
                logger.debug("Schedulers de verificación de estado configurados")
            except Exception as e:
                logger.error(f"Error configurando schedulers: {e}")

            # Configurar manejadores de señales (solo en escritorio)
            if not self._is_android:
                try:
                    self._setup_signal_handlers()
                    logger.debug("Manejadores de señales configurados")
                except Exception as e:
                    logger.warning(f"Error configurando manejadores de señales: {e}")
            
            # Iniciar servicio Android de forma segura
            if self._is_android:
                try:
                    self._start_android_service()
                except Exception as e:
                    logger.error(f"Error iniciando servicio Android: {e}")
            
            logger.info("FiscalberryApp inicializada exitosamente")
            
        except Exception as e:
            logger.error(f"Error crítico durante inicialización de FiscalberryApp: {e}", exc_info=True)
            # Inicializar valores mínimos para evitar errores adicionales
            if not hasattr(self, 'message_queue'):
                self.message_queue = queue.Queue()
            if not hasattr(self, '_stopping'):
                self._stopping = False
            if not hasattr(self, '_is_android'):
                self._is_android = False
            # No re-lanzar la excepción para evitar crash total
    
    def _detect_android(self):
        """Detecta si la app está corriendo en Android"""
        try:
            from jnius import autoclass
            return True
        except ImportError:
            return False
    
    def _request_android_permissions(self):
        """Solicita todos los permisos necesarios en Android automáticamente"""
        try:
            logger.info("="*70)
            logger.info("SOLICITANDO PERMISOS DE ANDROID")
            logger.info("="*70)
            
            # Importar módulos de permisos de forma segura
            try:
                from fiscalberry.common.android_permissions import (
                    request_all_permissions,
                    check_all_permissions
                )
                logger.debug("✓ Módulos de permisos importados correctamente")
            except ImportError as e:
                logger.warning(f"No se pudieron importar módulos de permisos: {e}")
                return
            
            # Verificar estado actual de permisos
            try:
                status = check_all_permissions()
                logger.info(f"Estado: {status['total_permissions']} permisos requeridos")
                logger.info(f"Otorgados: {status['total_permissions'] - status['missing_count']}")
                logger.info(f"Faltantes: {status['missing_count']}")
                
                if not status['all_granted']:
                    logger.info("⚠️ Solicitando permisos faltantes automáticamente...")
                    # Solicitar permisos directamente (aparecerán diálogos nativos de Android)
                    request_all_permissions(callback_on_complete=self._on_permissions_result)
                else:
                    logger.info("✅ Todos los permisos ya otorgados")
                    
            except Exception as e:
                logger.warning(f"Error verificando permisos: {e}")
            
            logger.info("="*70)
            
        except Exception as e:
            logger.error(f"Error general verificando permisos Android: {e}", exc_info=True)
    
    def _start_android_service(self):
        """Inicia el servicio Android en segundo plano"""
        try:
            logger.info("Intentando iniciar servicio Android...")
            
            # Método 1: AndroidService
            try:
                from android import AndroidService
                logger.debug("✓ AndroidService importado")
                
                service = AndroidService('Fiscalberry Service', 'running')
                service.start('Fiscalberry iniciado')
                logger.info("✓ Servicio Android iniciado")
                return
                
            except ImportError:
                logger.debug("AndroidService no disponible, probando método alternativo...")
            except Exception as e:
                logger.warning(f"Error con AndroidService: {e}")
            
            # Método 2: PythonService via jnius
            try:
                from jnius import autoclass
                logger.debug("✓ jnius importado")
                
                PythonService = autoclass('org.kivy.android.PythonService')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                
                activity = PythonActivity.mActivity
                if activity is not None:
                    PythonService.start(activity, '')
                    logger.info("✓ Servicio Android iniciado (método alternativo)")
                    return
                else:
                    logger.warning("PythonActivity.mActivity es None")
                    
            except ImportError:
                logger.debug("jnius no disponible")
            except Exception as e:
                logger.warning(f"Error con PythonService: {e}")
            
            # Si llegamos aquí, ningún método funcionó
            logger.warning("No se pudo iniciar servicio Android")
            logger.info("La app funcionará solo cuando esté en primer plano")
                
        except Exception as e:
            logger.error(f"Error general iniciando servicio Android: {e}", exc_info=True)
            # No re-lanzar la excepción para evitar crash de la app
    
    def build(self):
        """Construye la aplicación de forma optimizada."""
        logger.info("Construyendo interfaz de usuario...")
        
        # Detectar plataforma
        is_android = 'ANDROID_STORAGE' in os.environ or 'ANDROID_ARGUMENT' in os.environ
        logger.info(f"Plataforma detectada: {'Android' if is_android else 'Desktop'}")
        
        # Configurar título y icono
        self.title = "Servidor de Impresión"
        
        # Configurar el icono de la ventana de forma optimizada (solo Desktop)
        if not is_android:
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
        else:
            logger.debug("Android detectado - configuración de icono omitida")
        
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
        
        # Configurar el cierre de ventana (solo Desktop)
        if not is_android:
            try:
                from kivy.core.window import Window
                Window.bind(on_request_close=self._on_window_close)
            except Exception as e:
                logger.debug(f"No se pudo configurar cierre de ventana: {e}")
        
        # CRÍTICO: Determinar pantalla inicial basada en estado de adopción
        # (Los permisos se solicitan automáticamente en __init__)
        if self._configberry.is_comercio_adoptado():
            # Comercio YA adoptado → ir a main directamente
            sm.current = 'main'
            logger.info("Iniciando en pantalla principal (comercio adoptado)")
            # Iniciar servicios automáticamente
            self.on_start_service()
        else:
            # Comercio NO adoptado → enviar discover primero
            logger.info("Comercio no adoptado. Enviando discover...")
            
            # CRÍTICO: Enviar discover ANTES de mostrar adopt screen
            try:
                from fiscalberry.common.discover import send_discover
                send_discover()
                logger.info("Discover enviado exitosamente")
            except Exception as e:
                logger.error(f"Error al enviar discover: {e}")
            
            # NUEVO: Iniciar SocketIO para recibir configuración de adopción
            logger.info("Iniciando SocketIO para recibir adopción...")
            try:
                self._start_socketio_for_adoption()
            except Exception as e:
                logger.error(f"Error iniciando SocketIO: {e}", exc_info=True)
            
            # Ahora sí, mostrar pantalla de adopción
            sm.current = 'adopt'
            logger.info("Mostrando pantalla de adopción")
        
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
    
    def _start_socketio_for_adoption(self):
        """
        Inicia solo SocketIO (sin RabbitMQ) para recibir el evento de adopción.
        Solo inicia la conexión SocketIO para escuchar el evento start_rabbit.
        """
        try:
            from fiscalberry.common.fiscalberry_sio import FiscalberrySio
            
            uuid_value = self._configberry.get("SERVIDOR", "uuid", fallback="")
            sio_host = self._configberry.get("SERVIDOR", "sio_host", fallback="")
            
            if not uuid_value or not sio_host:
                logger.error("UUID o sio_host no configurados")
                return
            
            logger.info(f"Conectando SocketIO para adopción - Host: {sio_host}, UUID: {uuid_value[:8]}...")
            
            # Crear instancia de SocketIO
            sio_client = FiscalberrySio(
                server_url=sio_host,
                uuid=uuid_value,
                namespaces='/paxaprinter'
            )
            
            # Iniciar en thread separado
            Thread(target=sio_client.start, daemon=True).start()
            
            logger.info("✓ SocketIO iniciado para recibir adopción")
            
        except Exception as e:
            logger.error(f"Error iniciando SocketIO para adopción: {e}", exc_info=True)
    
    def on_start(self):
        """Se ejecuta después de que la aplicación inicie."""
        logger.info("Aplicación iniciada")
        
        # Detectar si estamos en Android
        is_android = 'ANDROID_STORAGE' in os.environ or 'ANDROID_ARGUMENT' in os.environ
        
        if is_android:
            logger.info("Android detectado - configurando permisos y servicios...")
            
            # CRÍTICO: Verificar Battery Exemption PRIMERO (antes de permisos regulares)
            # Sin esto, Doze mode matará el servicio en background
            self._check_and_request_battery_exemption()
            
            # Verificar y solicitar permisos regulares en Android
            try:
                from fiscalberry.android.permissions import (
                    check_all_permissions, 
                    request_all_permissions
                )
                
                perms = check_all_permissions()
                if not perms['all_granted']:
                    logger.warning("No todos los permisos están otorgados")
                    request_all_permissions()
            except Exception as e:
                logger.error(f"Error gestionando permisos Android: {e}")
        else:
            # Configuración de icono para Desktop (Windows)
            logger.info("Desktop detectado - configurando icono final...")
            try:
                icon_path = os.path.join(self.assetpath, "fiscalberry.ico")
                if os.path.exists(icon_path) and sys.platform == 'win32':
                    # Esperar un poco para que la ventana esté completamente inicializada
                    Clock.schedule_once(lambda dt: self._set_windows_icon_delayed(icon_path), 1)
            except Exception as e:
                logger.error(f"Error en on_start configurando icono: {e}")
    
    def _check_and_request_battery_exemption(self):
        """
        Verifica y solicita exclusión de optimización de batería.
        
        CRÍTICO: Esta es la defensa principal contra Doze mode.
        Sin esto, Android cortará la red del servicio después de 30 minutos.
        """
        try:
            from jnius import autoclass, cast
            
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Settings = autoclass('android.provider.Settings')
            PowerManager = autoclass('android.os.PowerManager')
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            Context = autoclass('android.content.Context')
            
            # NOTA: En jnius, clases internas de Java se acceden con $ (Build$VERSION)
            BuildVersion = autoclass('android.os.Build$VERSION')
            
            # Solo necesario en API 23+ (Android 6.0+)
            if BuildVersion.SDK_INT < 23:
                logger.info("API < 23 - Battery exemption no requerida")
                return
            
            activity = PythonActivity.mActivity
            if not activity:
                logger.warning("Activity no disponible para battery exemption")
                return
            
            package_name = activity.getPackageName()
            
            power_manager = activity.getSystemService(Context.POWER_SERVICE)
            power_manager = cast(PowerManager, power_manager)
            
            if power_manager.isIgnoringBatteryOptimizations(package_name):
                logger.info("✅ App ya excluida de optimización de batería")
                return
            
            # Mostrar warning al usuario
            logger.critical("⚠️ App NO excluida de optimización de batería")
            logger.critical("⚠️ El servicio puede ser terminado por Android en background")
            
            # Solicitar exclusión via Intent del sistema
            intent = Intent()
            intent.setAction(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            intent.setData(Uri.parse(f"package:{package_name}"))
            
            try:
                activity.startActivity(intent)
                logger.info("📱 Diálogo de exclusión de batería mostrado al usuario")
            except Exception as e:
                logger.error(f"Error mostrando diálogo de battery exemption: {e}")
                # Mostrar popup manual como fallback
                self._show_battery_exemption_warning()
                
        except ImportError:
            logger.debug("jnius no disponible - no es Android")
        except Exception as e:
            logger.error(f"Error verificando battery exemption: {e}", exc_info=True)
    
    def _show_battery_exemption_warning(self):
        """Muestra advertencia sobre battery exemption si el Intent falla."""
        try:
            from kivy.uix.popup import Popup
            from kivy.uix.label import Label
            from kivy.uix.button import Button
            from kivy.uix.boxlayout import BoxLayout
            
            content = BoxLayout(orientation='vertical', padding=10, spacing=10)
            content.add_widget(Label(
                text='⚠️ CONFIGURACIÓN CRÍTICA REQUERIDA ⚠️\n\n'
                     'Para que Fiscalberry funcione en segundo plano,\n'
                     'debes desactivar la optimización de batería:\n\n'
                     '1. Ir a Configuración → Apps → Fiscalberry\n'
                     '2. Batería → Sin restricciones\n\n'
                     'Sin esto, el servicio se detendrá automáticamente.',
                size_hint_y=0.8,
                halign='center'
            ))
            
            btn = Button(text='Entendido', size_hint_y=0.2)
            content.add_widget(btn)
            
            popup = Popup(
                title='Configuración Requerida',
                content=content,
                size_hint=(0.9, 0.6),
                auto_dismiss=False
            )
            
            btn.bind(on_press=popup.dismiss)
            popup.open()
            
        except Exception as e:
            logger.error(f"Error mostrando warning de battery exemption: {e}")
    
    def on_pause(self):
        """
        Llamado cuando la app pasa a background en Android.
        Retornar True para permitir pause sin cerrar la app.
        """
        logger.info("App pausada (background)")
        return True  # Importante para Android - permite que la app vuelva
    
    @mainthread
    def on_resume(self):
        """
        Llamado cuando la app vuelve de background en Android.
        
        CRÍTICO: Android destruye el contexto OpenGL (surfaceDestroyed en SDL).
        Un simple canvas.ask_update() NO es suficiente - debemos limpiar caches.
        
        Como NO tenemos imágenes (todas son strings vacíos), solo necesitamos:
        1. Limpiar caches de Kivy (texturas inválidas)
        2. Forzar recreación del canvas
        
        El decorador @mainthread es OBLIGATORIO.
        """
        logger.info("APP RESUMIDA - Recuperación de contexto OpenGL")
        
        try:
            from kivy.core.window import Window
            from kivy.cache import Cache
            
            # PASO 1: Limpiar caches de Kivy
            # Cuando SDL destruye la surface, las texturas en cache apuntan a memoria inválida
            logger.debug("Limpiando caches de Kivy...")
            
            try:
                Cache.remove('kv.texture')
                logger.debug("Cache kv.texture limpiada")
            except:
                pass
            
            try:
                Cache.remove('kv.image')
                logger.debug("Cache kv.image limpiada")
            except:
                pass
            
            try:
                Cache.remove('kv.atlas')
                logger.debug("Cache kv.atlas limpiada")
            except:
                pass
            
            # PASO 2: Forzar actualización de ventana
            Window.canvas.ask_update()
            logger.debug("Canvas de ventana actualizado")
            
            # PASO 3: Programar refrescos diferidos para asegurar recreación
            def refresh_ui(dt):
                try:
                    Window.canvas.ask_update()
                    if self.root and hasattr(self.root, 'canvas'):
                        self.root.canvas.ask_update()
                    logger.debug("UI refrescada")
                except Exception as e:
                    logger.error(f"Error refrescando UI: {e}")
            
            # Múltiples refreshes para asegurar éxito
            Clock.schedule_once(refresh_ui, 0.1)
            Clock.schedule_once(refresh_ui, 0.3)
            Clock.schedule_once(refresh_ui, 0.5)
            
            # PASO 4: Lógica específica de adopción
            if not hasattr(self, 'root') or not self.root:
                logger.warning("on_resume: self.root no disponible")
                return
            
            current_screen = self.root.current
            logger.info(f"Pantalla actual: {current_screen}")
            
            if current_screen == 'adopt':
                logger.info("Verificando adopción después de resumir...")
                screen = self.root.get_screen('adopt')
                if hasattr(screen, 'manual_check_adoption'):
                    Clock.schedule_once(
                        lambda dt: screen.manual_check_adoption(), 
                        0.5
                    )
            
            logger.info("Recuperación de contexto OpenGL completada")
            
        except Exception as e:
            logger.error(f"Error en on_resume: {e}", exc_info=True)
    

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

    def _on_permissions_result(self, success):
        """Callback cuando se completa la solicitud de permisos"""
        if success:
            logger.info("✅ Todos los permisos otorgados correctamente")
        else:
            logger.warning("⚠️ Algunos permisos fueron denegados")
            logger.warning("La aplicación puede tener funcionalidad limitada")
            # Mostrar toast o notificación en la UI actual
            self._show_permission_warning()
    
    def _show_permission_warning(self):
        """Muestra advertencia sobre permisos faltantes en la UI actual"""
        try:
            from kivy.uix.popup import Popup
            from kivy.uix.label import Label
            from kivy.uix.button import Button
            from kivy.uix.boxlayout import BoxLayout
            
            content = BoxLayout(orientation='vertical', padding=10, spacing=10)
            content.add_widget(Label(
                text='Algunos permisos no fueron otorgados.\n\n'
                     'La aplicación puede tener funcionalidad limitada.\n\n'
                     'Puedes otorgar los permisos desde:\n'
                     'Configuración → Apps → Fiscalberry → Permisos',
                size_hint_y=0.8
            ))
            
            btn = Button(text='Entendido', size_hint_y=0.2)
            content.add_widget(btn)
            
            popup = Popup(
                title='Permisos Faltantes',
                content=content,
                size_hint=(0.9, 0.5),
                auto_dismiss=False
            )
            
            btn.bind(on_press=popup.dismiss)
            popup.open()
            
        except Exception as e:
            logger.error(f"Error mostrando advertencia de permisos: {e}")

    def _on_permissions_denied(self, missing_permissions):
        """Callback cuando el usuario deniega permisos (legacy - no usado)"""
        logger.warning(f"Usuario denegó {len(missing_permissions)} permisos")
        logger.warning(f"Permisos faltantes: {missing_permissions}")

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