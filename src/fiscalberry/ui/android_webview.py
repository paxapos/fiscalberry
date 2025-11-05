"""
Helper para manejar WebView en Android
Coloca este archivo en: src/fiscalberry/ui/android_webview.py
"""

from kivy.utils import platform
from kivy.clock import Clock
from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger()

class AndroidWebViewManager:
    """Maneja la creación y gestión de WebViews en Android"""
    
    def __init__(self):
        self.webview = None
        self.webview_client = None
        self.callback = None
        
    def open_url(self, url, on_link_detected=None):
        """
        Abre una URL en un WebView de Android
        
        Args:
            url: URL a cargar
            on_link_detected: Callback cuando se detecta una URL de vinculación
        """
        if platform != 'android':
            logger.warning("WebView only available on Android")
            return False
        
        self.callback = on_link_detected
        
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            from android.runnable import run_on_ui_thread
            
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            WebView = autoclass('android.webkit.WebView')
            WebViewClient = autoclass('android.webkit.WebViewClient')
            WebSettings = autoclass('android.webkit.WebSettings')
            
            activity = PythonActivity.mActivity
            
            @run_on_ui_thread
            def create_webview():
                # Crear WebView
                self.webview = WebView(activity)
                settings = self.webview.getSettings()
                
                # Configurar WebView
                settings.setJavaScriptEnabled(True)
                settings.setDomStorageEnabled(True)
                settings.setDatabaseEnabled(True)
                settings.setLoadWithOverviewMode(True)
                settings.setUseWideViewPort(True)
                settings.setBuiltInZoomControls(False)
                settings.setSupportZoom(False)
                
                # Crear WebViewClient personalizado usando PythonJavaClass
                class CustomWebViewClient(PythonJavaClass):
                    __javainterfaces__ = ['android/webkit/WebViewClient']
                    __javacontext__ = 'app'
                    
                    def __init__(self, manager):
                        super().__init__()
                        self.manager = manager
                    
                    @java_method('(Landroid/webkit/WebView;Ljava/lang/String;)V')
                    def onPageFinished(self, view, url):
                        logger.info(f"Page loaded: {url}")
                        
                        # Verificar si es una URL de vinculación
                        if self.manager.callback and ('tenant=' in url or 'token=' in url):
                            logger.info("Link detected in URL")
                            Clock.schedule_once(lambda dt: self.manager.callback(url), 0.1)
                    
                    @java_method('(Landroid/webkit/WebView;Ljava/lang/String;)Z')
                    def shouldOverrideUrlLoading(self, view, url):
                        logger.info(f"Loading URL: {url}")
                        
                        # Si es una URL de vinculación, procesarla
                        if 'link-device' in url or 'adopt' in url:
                            if self.manager.callback:
                                Clock.schedule_once(lambda dt: self.manager.callback(url), 0.1)
                        
                        # Dejar que WebView maneje la carga
                        return False
                
                # Configurar cliente
                self.webview_client = CustomWebViewClient(self)
                self.webview.setWebViewClient(self.webview_client)
                
                # Cargar URL
                self.webview.loadUrl(url)
                
                logger.info(f"WebView created and loading: {url}")
            
            create_webview()
            return True
            
        except Exception as e:
            logger.error(f"Error creating WebView: {e}")
            return False
    
    def close(self):
        """Cierra y limpia el WebView"""
        if platform != 'android' or not self.webview:
            return
        
        try:
            from android.runnable import run_on_ui_thread
            
            @run_on_ui_thread
            def cleanup():
                if self.webview:
                    self.webview.destroy()
                    self.webview = None
                self.webview_client = None
                self.callback = None
                logger.info("WebView closed and cleaned up")
            
            cleanup()
            
        except Exception as e:
            logger.error(f"Error closing WebView: {e}")
    
    def get_webview_widget(self):
        """Retorna el WebView como widget (si está disponible)"""
        return self.webview
    
    def inject_javascript(self, js_code):
        """Inyecta código JavaScript en el WebView"""
        if platform != 'android' or not self.webview:
            return
        
        try:
            from android.runnable import run_on_ui_thread
            
            @run_on_ui_thread
            def inject():
                if self.webview:
                    self.webview.evaluateJavascript(js_code, None)
            
            inject()
            
        except Exception as e:
            logger.error(f"Error injecting JavaScript: {e}")
    
    def go_back(self):
        """Navega hacia atrás en el WebView"""
        if platform != 'android' or not self.webview:
            return
        
        try:
            from android.runnable import run_on_ui_thread
            
            @run_on_ui_thread
            def navigate_back():
                if self.webview and self.webview.canGoBack():
                    self.webview.goBack()
            
            navigate_back()
            
        except Exception as e:
            logger.error(f"Error going back: {e}")
    
    def reload(self):
        """Recarga la página actual"""
        if platform != 'android' or not self.webview:
            return
        
        try:
            from android.runnable import run_on_ui_thread
            
            @run_on_ui_thread
            def reload_page():
                if self.webview:
                    self.webview.reload()
            
            reload_page()
            
        except Exception as e:
            logger.error(f"Error reloading: {e}")