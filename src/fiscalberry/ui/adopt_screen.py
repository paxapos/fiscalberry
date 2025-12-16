import os
import sys
import threading
import time
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty

from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("GUI.AdoptScreen")

# Detectar plataforma
IS_ANDROID = 'ANDROID_STORAGE' in os.environ or 'ANDROID_ARGUMENT' in os.environ

# Importaciones condicionales
if IS_ANDROID:
    try:
        from jnius import autoclass
        from android import activity
        ANDROID_AVAILABLE = True
        logger.info("Módulos de Android disponibles")
    except ImportError:
        ANDROID_AVAILABLE = False
        logger.warning("Módulos de Android no disponibles")
else:
    ANDROID_AVAILABLE = False
    import webbrowser  # Solo para desktop
    logger.info("Modo Desktop - usando webbrowser")


configberry = Configberry()
host = configberry.get("SERVIDOR", "sio_host", "https://beta.paxapos.com")
uuid = configberry.get("SERVIDOR", "uuid", fallback="")

QRGENLINK = "https://codegenerator.paxapos.com/?bcid=qrcode&text="
ADOP_LINK = host + "/adopt/" + uuid


class AdoptScreen(Screen):
    """
    Pantalla de adopción de dispositivo.
    Compatible con Android y Desktop.
    """
    
    adoptarLink = StringProperty(ADOP_LINK)
    qrCodeLink = StringProperty(QRGENLINK + ADOP_LINK)
    is_monitoring = BooleanProperty(False)
    platform_name = StringProperty("Android" if IS_ANDROID else "Desktop")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._monitoring = False
        self._adoption_thread = None
        logger.info(f"AdoptScreen inicializada - Plataforma: {self.platform_name}")
    
    def on_pre_enter(self):
        """Se llama justo antes de entrar a la pantalla - útil para Android."""
        logger.info("Pre-entrada a pantalla de adopción")
        # Forzar refresh de la UI
        try:
            from kivy.core.window import Window
            Window.canvas.ask_update()
            logger.debug("Canvas actualizado en on_pre_enter")
        except Exception as e:
            logger.debug(f"No se pudo actualizar canvas: {e}")
    
    def on_enter(self):
        """
        Se llama cuando entramos a esta pantalla.
        Inicia el monitoreo automático de adopción.
        """
        logger.info(f"Entrando a pantalla de adopción en {self.platform_name}")
        
        # Actualizar links por si cambiaron
        self._update_links()
        
        # Iniciar monitoreo de adopción
        if not self._monitoring:
            self._monitoring = True
            self.is_monitoring = True
            self._start_adoption_monitoring()
            logger.info("Monitoreo de adopción iniciado")
    
    def on_leave(self):
        """
        Se llama cuando salimos de esta pantalla.
        Detiene el monitoreo.
        """
        logger.info("Saliendo de pantalla de adopción")
        self._monitoring = False
        self.is_monitoring = False
    
    def _update_links(self):
        """Actualiza los links de adopción con la configuración actual."""
        try:
            host = configberry.get("SERVIDOR", "sio_host", "https://beta.paxapos.com")
            uuid_val = configberry.get("SERVIDOR", "uuid", fallback="")
            
            if uuid_val:
                self.adoptarLink = f"{host}/adopt/{uuid_val}"
                self.qrCodeLink = f"{QRGENLINK}{self.adoptarLink}"
                logger.debug(f"Links actualizados - UUID: {uuid_val[:8]}...")
            else:
                logger.warning("UUID no disponible para generar links")
        except Exception as e:
            logger.error(f"Error actualizando links: {e}")
    
    def open_adoption_link(self):
        """
        Abre el link de adopción en el navegador.
        Usa Intent para Android o webbrowser para Desktop.
        """
        try:
            url = self.adoptarLink
            
            if IS_ANDROID and ANDROID_AVAILABLE:
                # Usar Intent de Android
                success = self._open_url_android(url)
                if success:
                    logger.info(f"Link abierto en Android: {url}")
                else:
                    logger.error("No se pudo abrir el link en Android")
            else:
                # Usar webbrowser para Desktop
                import webbrowser
                webbrowser.open(url)
                logger.info(f"Link abierto en Desktop: {url}")
                
        except Exception as e:
            logger.error(f"Error al abrir navegador: {e}", exc_info=True)
    
    def _open_url_android(self, url):
        """
        Abre una URL usando Intent de Android.
        
        Args:
            url: URL a abrir
            
        Returns:
            bool: True si se abrió exitosamente, False en caso contrario
        """
        try:
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            
            intent = Intent()
            intent.setAction(Intent.ACTION_VIEW)
            intent.setData(Uri.parse(url))
            
            # Obtener la actividad actual usando PythonActivity
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            currentActivity = PythonActivity.mActivity
            currentActivity.startActivity(intent)
            
            logger.info("Intent de Android lanzado exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"Error abriendo URL con Intent: {e}", exc_info=True)
            return False
    
    def _start_adoption_monitoring(self):
        """
        Inicia el monitoreo de adopción en un thread separado.
        Verifica cada 2 segundos si el comercio fue adoptado.
        
        IMPORTANTE: Este thread NO debe hacer operaciones de UI.
        Todas las operaciones de UI se hacen mediante Clock.schedule_once.
        """
        def monitor():
            logger.info("Thread de monitoreo de adopción iniciado")
            check_count = 0
            check_interval = 3 if IS_ANDROID else 2  # Android: 3s, Desktop: 2s
            
            while self._monitoring:
                time.sleep(check_interval)
                check_count += 1
                
                try:
                    if configberry.is_comercio_adoptado():
                        logger.info("¡Comercio adoptado detectado! Redirigiendo a main...")
                        self._monitoring = False
                        self.is_monitoring = False
                        
                        # CRÍTICO: Cambiar a pantalla main en el thread principal de Kivy
                        Clock.schedule_once(self._go_to_main, 0)
                        break
                    
                    # Log cada 30 segundos para debugging
                    if check_count % 15 == 0:
                        logger.debug(f"Monitoreo activo - Verificación #{check_count}")
                        
                except Exception as e:
                    logger.error(f"Error en monitoreo de adopción: {e}")
                    time.sleep(5)  # Esperar más tiempo si hay error
            
            logger.info("Thread de monitoreo de adopción finalizado")
        
        # Iniciar thread daemon (se cierra automáticamente con la app)
        self._adoption_thread = threading.Thread(target=monitor, daemon=True)
        self._adoption_thread.start()
    
    def _go_to_main(self, dt):
        """
        Cambia a la pantalla main después de adopción exitosa.
        
        ⚠️ IMPORTANTE: Este método DEBE ejecutarse en el thread principal de Kivy.
        Por eso se llama mediante Clock.schedule_once().
        
        Args:
            dt: Delta time (requerido por Clock.schedule_once)
        """
        try:
            app = App.get_running_app()
            app.updatePropertiesWithConfig()
            
            if self.manager:
                self.manager.current = 'main'
            else:
                logger.error("ScreenManager no disponible")
                return
            
            app.on_start_service()
            
            if IS_ANDROID and hasattr(app, '_start_android_service'):
                try:
                    app._start_android_service()
                except Exception as e:
                    logger.error(f"Error servicio Android: {e}")
            
            logger.info("Pantalla main OK")
            
        except Exception as e:
            logger.error(f"Error al ir a main: {e}", exc_info=True)
    
    def manual_check_adoption(self):
        """
        Verifica manualmente si el comercio fue adoptado.
        Útil para un botón de "Verificar Adopción" en la UI.
        """
        try:
            logger.info("[Verificación manual] Comprobando estado de adopción...")
            
            # Verificar si existe la sección Paxaprinter
            has_section = configberry.config.has_section("Paxaprinter")
            logger.debug(f"[Verificación manual] Sección Paxaprinter existe: {has_section}")
            
            if has_section:
                # Verificar tenant
                tenant = configberry.get("Paxaprinter", "tenant", fallback="")
                logger.debug(f"[Verificación manual] Tenant configurado: '{tenant}' (longitud: {len(tenant)})")
            else:
                logger.debug("[Verificación manual] No hay sección Paxaprinter en la configuración")
            
            # Verificar estado final
            is_adopted = configberry.is_comercio_adoptado()
            logger.info(f"[Verificación manual] is_comercio_adoptado() retornó: {is_adopted}")
            
            if is_adopted:
                logger.info("[Verificación manual] ✅ Comercio adoptado - Redirigiendo a main...")
                Clock.schedule_once(self._go_to_main, 0)
            else:
                logger.info("[Verificación manual] ⏳ Comercio aún no adoptado")
                # Aquí podrías mostrar un mensaje al usuario
        except Exception as e:
            logger.error(f"Error en verificación manual: {e}", exc_info=True)


