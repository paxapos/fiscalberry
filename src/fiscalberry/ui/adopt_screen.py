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
        logger.debug("Módulos de Android disponibles")
    except ImportError:
        ANDROID_AVAILABLE = False
        logger.warning("Módulos de Android no disponibles")
else:
    ANDROID_AVAILABLE = False
    import webbrowser  # Solo para desktop
    logger.debug("Modo Desktop - usando webbrowser")


configberry = Configberry()
host = configberry.get("SERVIDOR", "sio_host", "https://beta.paxapos.com")
uuid = configberry.get("SERVIDOR", "uuid", fallback="")

# Fallback remoto: solo si por algún motivo no se puede generar el QR local.
QRGENLINK = "https://codegenerator.paxapos.com/?bcid=qrcode&text="
ADOP_LINK = host + "/adopt/" + uuid


def link_de_adopcion_valido(url):
    """
    ¿Este link identifica a un dispositivo?

    Un link que termina en `/adopt/` (sin uuid) hace que el servidor responda
    500 — `ArgumentCountError: Too few arguments to adopt()` — y el usuario ve
    una pantalla de error sin ninguna pista. Pasó en producción: el config.ini
    se quedó sin uuid y la pantalla ofreció igual el botón de vincular.
    """
    if not url:
        return False
    return not url.rstrip("/").endswith("/adopt")


def generar_qr(texto):
    """
    Genera el QR de vinculación LOCALMENTE y devuelve la ruta del PNG.

    Antes se cargaba como imagen remota desde codegenerator.paxapos.com: si el
    DNS o la red fallan justo al abrir la app (pasa seguido en el arranque, o en
    un local con la wifi todavía negociando), la pantalla de vinculación muestra
    una imagen rota y no hay forma de vincular. La librería qrcode ya viene
    empaquetada en el APK, así que no hace falta pedirlo por red.
    """
    try:
        import hashlib
        import qrcode

        # El nombre incluye un hash del link: Kivy cachea las imágenes por ruta,
        # así que un archivo de nombre fijo mostraría el QR viejo si cambia el
        # uuid o el host.
        firma = hashlib.sha1(texto.encode("utf-8")).hexdigest()[:8]
        destino = os.path.join(
            os.path.dirname(configberry.getConfigFIle()), f"adopt_qr_{firma}.png"
        )
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(texto)
        qr.make(fit=True)
        qr.make_image(fill_color="black", back_color="white").save(destino)
        logger.debug(f"QR generado localmente en {destino}")
        return destino
    except Exception as e:
        logger.error(f"No se pudo generar el QR local, se usa el remoto: {e}")
        return QRGENLINK + texto


class AdoptScreen(Screen):
    """
    Pantalla de adopción de dispositivo.
    Compatible con Android y Desktop.
    """
    
    adoptarLink = StringProperty(ADOP_LINK)
    qrCodeLink = StringProperty("")
    # Mensaje visible cuando la vinculación no se puede preparar. Vacío = todo ok.
    linkError = StringProperty("")
    is_monitoring = BooleanProperty(False)
    platform_name = StringProperty("Android" if IS_ANDROID else "Desktop")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._monitoring = False
        self._adoption_thread = None
        # Si el discover del arranque ya registró el dispositivo. Mientras sea
        # False, abrir el link reintenta el registro antes de mandar al usuario
        # a una página que va a fallar.
        self._registrado = False
        logger.debug(f"AdoptScreen inicializada - Plataforma: {self.platform_name}")
    
    def on_pre_enter(self):
        """Se llama justo antes de entrar a la pantalla - útil para Android."""
        logger.debug("Pre-entrada a pantalla de adopción")
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
        logger.debug(f"Entrando a pantalla de adopción en {self.platform_name}")
        
        # Actualizar links por si cambiaron
        self._update_links()
        
        # Iniciar monitoreo de adopción
        if not self._monitoring:
            self._monitoring = True
            self.is_monitoring = True
            self._start_adoption_monitoring()
            logger.debug("Monitoreo de adopción iniciado")
    
    def on_leave(self):
        """
        Se llama cuando salimos de esta pantalla.
        Detiene el monitoreo.
        """
        logger.debug("Saliendo de pantalla de adopción")
        self._monitoring = False
        self.is_monitoring = False
    
    def _update_links(self):
        """
        Actualiza los links de adopción con la configuración actual.

        Si falta el uuid hay que RECUPERARSE, no solo avisar al log: antes, sin
        uuid, la pantalla dejaba el link de clase (`host + "/adopt/" + ""`), o
        sea `/adopt/` sin identificador. El usuario veía un botón normal, lo
        apretaba y el servidor respondía 500 (`ArgumentCountError: Too few
        arguments to adopt()`), sin ninguna pista de qué había pasado. Y el QR
        quedaba en blanco por el mismo motivo.
        """
        try:
            host = configberry.get("SERVIDOR", "sio_host", "https://beta.paxapos.com")
            uuid_val = configberry.get("SERVIDOR", "uuid", fallback="")

            if not uuid_val:
                logger.warning("No hay uuid en la configuración; se regenera.")
                uuid_val = self._regenerar_uuid()

            if uuid_val:
                self.adoptarLink = f"{host}/adopt/{uuid_val}"
                self.qrCodeLink = generar_qr(self.adoptarLink)
                self.linkError = ""
                logger.debug(f"Links actualizados - UUID: {uuid_val[:8]}...")
            else:
                # Mejor un mensaje explícito que un botón que lleva a un error
                # del servidor.
                self.adoptarLink = ""
                self.qrCodeLink = ""
                self.linkError = ("No se pudo generar el identificador de este "
                                  "dispositivo. Reiniciá la aplicación.")
                logger.error("UUID no disponible ni regenerable: "
                             "la vinculación no puede continuar.")
        except Exception as e:
            logger.error(f"Error actualizando links: {e}", exc_info=True)
            self.linkError = f"Error preparando la vinculación: {e}"

    def registrar_en_servidor(self):
        """
        Reintenta el registro (discover) y refleja el resultado en pantalla.

        Sin registro previo, el servidor no tiene una Paxaprinter con este uuid
        y la vinculación termina en ":: Paxaprinter no encontrada" — un error
        del servidor que no le dice nada al usuario sobre qué falló ni qué
        hacer. Con esto el estado queda a la vista y se puede reintentar sin
        reinstalar.
        """
        try:
            from fiscalberry.common.discover import send_discover

            if send_discover():
                self.linkError = ""
                logger.info("Dispositivo registrado en el servidor.")
                return True

            self.linkError = ("No se pudo registrar el dispositivo en el "
                              "servidor. Revisá la conexión y reintentá.")
            logger.error("El discover no pudo registrar el dispositivo.")
            return False
        except Exception as e:
            self.linkError = f"No se pudo contactar al servidor: {e}"
            logger.error(f"Error registrando el dispositivo: {e}", exc_info=True)
            return False

    def _regenerar_uuid(self):
        """
        Vuelve a darle identidad al dispositivo cuando el config.ini la perdió.

        En Android es recuperable sin costo: el uuid se deriva de ANDROID_ID, así
        que el que se regenera es EL MISMO de antes y no hay que re-vincular.
        """
        try:
            from fiscalberry.common.device_uuid import generate_device_uuid

            nuevo = generate_device_uuid()
            configberry.set("SERVIDOR", {"uuid": nuevo})
            logger.info(f"UUID regenerado: {nuevo[:8]}...")
            return nuevo
        except Exception as e:
            logger.error(f"No se pudo regenerar el uuid: {e}", exc_info=True)
            return ""
    
    def open_adoption_link(self):
        """
        Abre el link de adopción en el navegador.
        Usa Intent para Android o webbrowser para Desktop.
        """
        try:
            url = self.adoptarLink

            if not link_de_adopcion_valido(url):
                self.linkError = ("La vinculación todavía no está lista. "
                                  "Reiniciá la aplicación.")
                logger.error("Se intentó abrir un link de adopción sin uuid: %r", url)
                return

            # El servidor solo conoce este dispositivo si el discover llegó. Se
            # reintenta acá, en el momento exacto en que hace falta: si el
            # registro del arranque falló (sin red, permisos, lo que sea), el
            # usuario abriría el link para encontrarse con "Paxaprinter no
            # encontrada" y ninguna explicación.
            if not self._registrado:
                self._registrado = self.registrar_en_servidor()
                if not self._registrado:
                    return

            if IS_ANDROID and ANDROID_AVAILABLE:
                # Usar Intent de Android
                success = self._open_url_android(url)
                if success:
                    logger.debug(f"Link abierto en Android")
                else:
                    logger.error("No se pudo abrir el link en Android")
            else:
                # Usar webbrowser para Desktop
                import webbrowser
                webbrowser.open(url)
                logger.debug("Link abierto en Desktop")
                
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
            
            logger.debug("Intent de Android lanzado")
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
            logger.debug("Thread de monitoreo de adopción iniciado")
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
            
            logger.debug("Thread de monitoreo de adopción finalizado")
        
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
            logger.debug("Comprobando estado de adopción...")
            
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
            logger.debug(f"is_comercio_adoptado(): {is_adopted}")
            
            if is_adopted:
                logger.info("[Verificación manual] ✅ Comercio adoptado - Redirigiendo a main...")
                Clock.schedule_once(self._go_to_main, 0)
            else:
                logger.info("[Verificación manual] ⏳ Comercio aún no adoptado")
                # Aquí podrías mostrar un mensaje al usuario
        except Exception as e:
            logger.error(f"Error en verificación manual: {e}", exc_info=True)


