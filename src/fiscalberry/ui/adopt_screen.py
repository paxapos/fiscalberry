import os
import requests
import json
from kivy.uix.screenmanager import Screen
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.app import App
from kivy.clock import Clock
from kivy.utils import platform
from kivy.metrics import dp
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.fiscalberry_logger import getLogger
from kivy.properties import StringProperty

logger = getLogger()
configberry = Configberry()
host = configberry.get("SERVIDOR", "sio_host", "https://beta.paxapos.com")
uuid = configberry.get("SERVIDOR", "uuid", fallback="")

QRGENLINK = "https://codegenerator.paxapos.com/?bcid=qrcode&text="
SIMPLE_LINK = "https://beta.paxapos.com"

class AdoptScreen(Screen):
    adoptarLink = StringProperty(SIMPLE_LINK)
    qrCodeLink = StringProperty(QRGENLINK + SIMPLE_LINK)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.check_event = None
        self.check_url_event = None
        self.popup = None
        self.android_webview = None
        self.android_layout = None
    
    def on_enter(self):
        """Cuando entramos a esta pantalla, iniciamos el polling"""
        logger.info("AdoptScreen: Pantalla activada, iniciando polling")
        if not self.check_event:
            self.check_event = Clock.schedule_interval(self._check_if_linked, 3)
    
    def on_leave(self):
        """Cuando salimos de la pantalla, detenemos el polling"""
        if self.check_event:
            self.check_event.cancel()
            self.check_event = None
        if self.check_url_event:
            self.check_url_event.cancel()
            self.check_url_event = None
        if self.popup:
            self.popup.dismiss()
    
    def open_web_login(self):
        """Abre el login web - WebView en Android"""
        logger.info(f"open_web_login LLAMADO! URL: {self.adoptarLink}")
        if platform == 'android':
            logger.info("Plataforma Android detectada")
            self._open_android_webview_simple()
        else:
            logger.info("Plataforma Desktop")
            self._show_desktop_instructions()
    
    def _show_desktop_instructions(self):
        """Muestra instrucciones para desktop"""
        content = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))
        content.add_widget(Label(
            text=f"Abre este link en tu navegador:\n\n{self.adoptarLink}",
            size_hint_y=0.8
        ))
        btn = Button(text="Cerrar", size_hint_y=0.2)
        content.add_widget(btn)
        
        popup = Popup(
            title="Vinculación de Dispositivo",
            content=content,
            size_hint=(0.8, 0.4)
        )
        btn.bind(on_press=popup.dismiss)
        popup.open()
    
    def _open_android_webview_simple(self):
        """Crea WebView sin WebViewClient personalizado, usa polling de URL"""
        try:
            logger.info("=== INICIO WebView Simple con polling de URL ===")
            from jnius import autoclass
            from android.runnable import run_on_ui_thread
            
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            context = activity.getApplicationContext()
            
            WebView = autoclass('android.webkit.WebView')
            WebSettings = autoclass('android.webkit.WebSettings')
            LayoutParams = autoclass('android.view.ViewGroup$LayoutParams')
            FrameLayout = autoclass('android.widget.FrameLayout')
            Color = autoclass('android.graphics.Color')
            
            @run_on_ui_thread
            def create_webview():
                try:
                    logger.info(">>> Creando WebView simple")
                    
                    # Crear contenedor
                    container = FrameLayout(context)
                    container.setBackgroundColor(Color.WHITE)
                    
                    # Crear WebView
                    webview = WebView(context)
                    settings = webview.getSettings()
                    
                    # Configuración completa
                    settings.setJavaScriptEnabled(True)
                    settings.setDomStorageEnabled(True)
                    settings.setDatabaseEnabled(True)
                    settings.setLoadWithOverviewMode(True)
                    settings.setUseWideViewPort(True)
                    settings.setBuiltInZoomControls(False)
                    settings.setSupportZoom(False)
                    settings.setCacheMode(settings.LOAD_NO_CACHE)
                    
                    # Configurar layout
                    webview_params = LayoutParams(
                        LayoutParams.MATCH_PARENT,
                        LayoutParams.MATCH_PARENT
                    )
                    webview.setLayoutParams(webview_params)
                    
                    # Agregar al contenedor
                    container.addView(webview)
                    
                    # Agregar a la actividad
                    activity.addContentView(
                        container,
                        LayoutParams(
                            LayoutParams.MATCH_PARENT,
                            LayoutParams.MATCH_PARENT
                        )
                    )
                    
                    # Guardar referencias
                    self.android_webview = webview
                    self.android_layout = container
                    
                    # Cargar URL
                    logger.info(f"🌐 Cargando URL: {self.adoptarLink}")
                    webview.loadUrl(self.adoptarLink)
                    
                    logger.info("=== WebView creado EXITOSAMENTE ===")
                    
                    # Iniciar polling de URL cada 2 segundos
                    if self.check_url_event:
                        self.check_url_event.cancel()
                    self.check_url_event = Clock.schedule_interval(self._check_webview_url, 2)
                    logger.info("📍 Polling de URL iniciado")
                    
                    # Crear popup informativo
                    def create_info_popup():
                        content = BoxLayout(orientation='vertical', padding=dp(10))
                        label = Label(
                            text='Inicia sesión en la ventana.\nSe cerrará automáticamente al vincular.',
                            size_hint_y=0.5,
                            color=(0.2, 0.2, 0.2, 1)
                        )
                        close_btn = Button(
                            text='Cerrar Manualmente',
                            size_hint_y=0.3,
                            on_press=lambda x: self._close_webview()
                        )
                        content.add_widget(label)
                        content.add_widget(close_btn)
                        
                        self.popup = Popup(
                            title='Navegador Web',
                            content=content,
                            size_hint=(0.9, 0.25),
                            auto_dismiss=False,
                            pos_hint={'top': 1}
                        )
                        self.popup.open()
                    
                    Clock.schedule_once(lambda dt: create_info_popup(), 0.3)
                    
                except Exception as e:
                    logger.error(f"!!! ERROR en create_webview: {e}", exc_info=True)
            
            create_webview()
            
        except Exception as e:
            logger.error(f"!!! ERROR FATAL: {e}", exc_info=True)
    
    def _check_webview_url(self, dt):
        """Verifica la URL actual del WebView mediante JavaScript"""
        if not self.android_webview:
            return False  # Detener si no hay webview
        
        try:
            from android.runnable import run_on_ui_thread
            
            # JavaScript para obtener la URL actual y datos del localStorage
            js_code = """
            (function() {
                try {
                    var currentUrl = window.location.href;
                    var tenant = localStorage.getItem('tenant') || '';
                    var siteName = localStorage.getItem('site_name') || '';
                    var alias = localStorage.getItem('alias') || '';
                    
                    return JSON.stringify({
                        url: currentUrl,
                        tenant: tenant,
                        site_name: siteName,
                        alias: alias
                    });
                } catch(e) {
                    return JSON.stringify({url: '', error: e.toString()});
                }
            })();
            """
            
            @run_on_ui_thread
            def check_url():
                try:
                    # Obtener URL directamente del WebView
                    url = self.android_webview.getUrl()
                    
                    if url:
                        logger.info(f"📍 URL actual: {url}")
                        
                        # Verificar si contiene parámetros de vinculación
                        if any(param in url.lower() for param in ['tenant=', 'site_name=', 'alias=', 'token=']):
                            logger.info("🎯 VINCULACIÓN DETECTADA en URL!")
                            Clock.schedule_once(lambda dt: self._process_link_url(url), 0.1)
                            return
                        
                        # Si estamos en home/dashboard, intentar obtener del localStorage
                        if 'paxapos.com/home' in url.lower() or 'paxapos.com/dashboard' in url.lower():
                            logger.info("🏠 En página principal, verificando localStorage")
                            # Ejecutar JS para revisar localStorage
                            self._check_localstorage()
                
                except Exception as e:
                    logger.error(f"Error verificando URL: {e}")
            
            check_url()
            
        except Exception as e:
            logger.error(f"Error en _check_webview_url: {e}")
        
        return True  # Continuar polling
    
    def _check_localstorage(self):
        """Verifica si hay datos de vinculación en localStorage"""
        try:
            from android.runnable import run_on_ui_thread
            
            js_code = """
            (function() {
                var tenant = localStorage.getItem('tenant');
                var siteName = localStorage.getItem('site_name'); 
                var alias = localStorage.getItem('alias');
                
                if (tenant) {
                    window.location.href = 'fiscalberry://link?tenant=' + tenant + 
                        '&site_name=' + (siteName || '') + 
                        '&alias=' + (alias || '');
                }
            })();
            """
            
            @run_on_ui_thread
            def inject_js():
                if self.android_webview:
                    self.android_webview.loadUrl(f"javascript:{js_code}")
            
            inject_js()
            
        except Exception as e:
            logger.error(f"Error verificando localStorage: {e}")
    
    def _close_webview(self):
        """Cierra el WebView de Android"""
        logger.info("=== CERRANDO WEBVIEW ===")
        
        # Detener polling de URL
        if self.check_url_event:
            self.check_url_event.cancel()
            self.check_url_event = None
        
        if platform == 'android' and self.android_layout:
            try:
                from jnius import autoclass
                from android.runnable import run_on_ui_thread
                
                @run_on_ui_thread
                def remove_webview():
                    try:
                        PythonActivity = autoclass('org.kivy.android.PythonActivity')
                        activity = PythonActivity.mActivity
                        
                        content_view = activity.findViewById(0x01020002)
                        if content_view:
                            content_view.removeView(self.android_layout)
                            logger.info("Layout removido")
                        
                        if self.android_webview:
                            self.android_webview.destroy()
                            logger.info("WebView destruido")
                        
                        self.android_webview = None
                        self.android_layout = None
                        
                        logger.info("=== WEBVIEW CERRADO EXITOSAMENTE ===")
                    except Exception as e:
                        logger.error(f"Error removiendo WebView: {e}", exc_info=True)
                
                remove_webview()
            except Exception as e:
                logger.error(f"Error en _close_webview: {e}", exc_info=True)
        
        if self.popup:
            self.popup.dismiss()
            self.popup = None
    
    def _process_link_url(self, url):
        """Procesa una URL de vinculación detectada"""
        try:
            from urllib.parse import urlparse, parse_qs
            
            logger.info(f"=== PROCESANDO URL DE VINCULACION ===")
            logger.info(f"URL: {url}")
            
            # Manejar el esquema personalizado fiscalberry://
            if url.startswith('fiscalberry://'):
                url = url.replace('fiscalberry://', 'https://')
            
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            
            logger.info(f"Parámetros encontrados: {params}")
            
            saved = False
            
            if 'tenant' in params:
                tenant = params['tenant'][0]
                logger.info(f">>> Guardando tenant: {tenant}")
                configberry.writeKeyForSection("Paxaprinter", "tenant", tenant)
                saved = True
            
            if 'site_name' in params:
                site_name = params['site_name'][0]
                logger.info(f">>> Guardando site_name: {site_name}")
                configberry.writeKeyForSection("Paxaprinter", "site_name", site_name)
                saved = True
            
            if 'alias' in params:
                alias = params['alias'][0]
                logger.info(f">>> Guardando alias: {alias}")
                configberry.writeKeyForSection("Paxaprinter", "alias", alias)
                saved = True
            
            if saved:
                logger.info("!!! VINCULACION EXITOSA !!!")
                
                # Actualizar app
                app = App.get_running_app()
                app.updatePropertiesWithConfig()
                
                # Cerrar y navegar INMEDIATAMENTE
                Clock.schedule_once(lambda dt: self._close_and_navigate(), 0.2)
            else:
                logger.warning("No se guardaron parámetros, URL inválida")
        
        except Exception as e:
            logger.error(f"Error procesando URL: {e}", exc_info=True)
    
    def _check_if_linked(self, dt):
        """Verifica periódicamente si el dispositivo ya fue vinculado"""
        try:
            if not hasattr(configberry, 'configFilePath') or not configberry.configFilePath:
                return True
            
            # Recargar config
            configberry.config.read(configberry.configFilePath)
            
            # Verificar si hay tenant
            tenant = configberry.get("Paxaprinter", "tenant", fallback="")
            
            if tenant and tenant != "":
                logger.info(f"!!! DISPOSITIVO VINCULADO (via polling)! Tenant: {tenant} !!!")
                
                # Actualizar app
                app = App.get_running_app()
                app.updatePropertiesWithConfig()
                
                # Cerrar y navegar
                self._close_and_navigate()
                return False  # Detener el evento
            else:
                if not hasattr(self, '_poll_count'):
                    self._poll_count = 0
                self._poll_count += 1
                
                if self._poll_count % 10 == 0:
                    logger.info(f"[Polling #{self._poll_count}] Esperando vinculación...")
        
        except Exception as e:
            logger.error(f"Error verificando vinculación: {e}")
        
        return True  # Continuar polling
    
    def _close_and_navigate(self):
        """Cierra todo y navega a main"""
        logger.info("=== NAVEGANDO A MAIN ===")
        
        # Cerrar webview
        self._close_webview()
        
        # Detener polling
        if self.check_event:
            self.check_event.cancel()
            self.check_event = None
        
        # Navegar
        app = App.get_running_app()
        if app.root and hasattr(app.root, 'current'):
            app.root.current = "main"
            logger.info("✅ Navegación a main completada")