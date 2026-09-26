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
    # True mientras el botón reintenta el registro en segundo plano.
    registrando = BooleanProperty(False)
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
        self._registro_thread = None
        logger.debug(f"AdoptScreen inicializada - Plataforma: {self.platform_name}")

    def marcar_registrado(self, registrado=True):
        """
        Informa el resultado del discover que hizo la app al arrancar.

        Sin esto la pantalla nunca se enteraba de que el dispositivo ya estaba
        registrado y cada click en "Abrir vinculación" volvía a mandar el
        discover (ver issue #191).
        """
        self._registrado = bool(registrado)
    
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

    def ir_a_logs(self):
        """
        Abre el registro desde la pantalla de vinculación.

        Hasta ahora los logs solo eran accesibles desde la pantalla principal,
        a la que se llega **después** de vincular. O sea que cuando la
        vinculación fallaba —el único momento en que hacen falta— no había
        forma de verlos desde el dispositivo.
        """
        try:
            if not self.manager:
                logger.error("Sin ScreenManager: no se puede abrir el registro.")
                return
            pantalla_logs = self.manager.get_screen("logs")
            # Para que "Volver" traiga de vuelta acá y no a 'main', que todavía
            # no es un destino válido.
            pantalla_logs.volver_a = self.name or "adopt"
            self.manager.current = "logs"
        except Exception as e:
            logger.error(f"No se pudo abrir la pantalla de registro: {e}",
                         exc_info=True)
            self.linkError = f"No se pudo abrir el registro: {e}"

    def registrar_en_servidor(self):
        """
        Reintenta el registro (discover) y refleja el resultado en pantalla.

        Sin registro previo, el servidor no tiene una Paxaprinter con este uuid
        y la vinculación termina en ":: Paxaprinter no encontrada" — un error
        del servidor que no le dice nada al usuario sobre qué falló ni qué
        hacer. Con esto el estado queda a la vista y se puede reintentar sin
        reinstalar.
        """
        ok, mensaje = self._intentar_registro()
        self.linkError = mensaje
        return ok

    def _intentar_registro(self):
        """
        Manda el discover y devuelve (ok, mensaje_de_error).

        No toca la UI: se puede llamar desde un hilo que no es el de Kivy.
        """
        try:
            from fiscalberry.common.discover import send_discover

            if send_discover():
                logger.info("Dispositivo registrado en el servidor.")
                return True, ""

            logger.error("El discover no pudo registrar el dispositivo.")
            return False, ("No se pudo registrar el dispositivo en el "
                           "servidor. Revisá la conexión y reintentá.")
        except Exception as e:
            logger.error(f"Error registrando el dispositivo: {e}", exc_info=True)
            return False, f"No se pudo contactar al servidor: {e}"

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

        El link se abre SIEMPRE que sea válido, igual que el QR (issue #191).
        Antes, si el dispositivo no figuraba como registrado, se reenviaba el
        discover en el hilo de Kivy (UI congelada hasta 30 s) y, si fallaba,
        el botón se negaba a abrir el link: la adopción solo andaba con el QR,
        aunque el dispositivo ya estuviera registrado en el servidor.
        """
        try:
            url = self.adoptarLink

            if not link_de_adopcion_valido(url):
                self.linkError = ("La vinculación todavía no está lista. "
                                  "Reiniciá la aplicación.")
                logger.error("Se intentó abrir un link de adopción sin uuid: %r", url)
                return

            if self._registrado:
                self._abrir_link(url)
                return

            # Ya hay un reintento en curso: un segundo click no lanza otro.
            if self.registrando:
                return

            # El servidor solo conoce este dispositivo si el discover llegó, así
            # que se reintenta antes de abrir; pero en otro hilo, y sin que un
            # fallo impida abrir el link.
            self.registrando = True
            self.linkError = ""
            self._registro_thread = threading.Thread(
                target=self._registrar_y_abrir, args=(url,), daemon=True
            )
            self._registro_thread.start()

        except Exception as e:
            self.registrando = False
            self.linkError = f"No se pudo abrir la vinculación: {e}"
            logger.error(f"Error al abrir navegador: {e}", exc_info=True)

    def _registrar_y_abrir(self, url):
        """Hilo de fondo: reintenta el discover y vuelve al hilo de Kivy."""
        ok, mensaje = self._intentar_registro()
        Clock.schedule_once(lambda dt: self._fin_registro(url, ok, mensaje), 0)

    def _fin_registro(self, url, ok, mensaje):
        """Hilo de Kivy: refleja el resultado del registro y abre el link."""
        self.registrando = False
        self._registrado = ok
        if not ok:
            # Aviso, no bloqueo: el dispositivo puede estar registrado de antes
            # (el QR funciona justamente por eso).
            self.linkError = (f"{mensaje} Se abrió la vinculación igual; si la "
                              "página no encuentra el dispositivo, reintentá.")
        self._abrir_link(url)

    def _abrir_link(self, url):
        """
        Abre la URL en el navegador del sistema.

        Si no se puede, lo dice en pantalla con el link y la alternativa del
        QR, en vez de dejarlo solo en el log.
        """
        try:
            if IS_ANDROID and ANDROID_AVAILABLE:
                abierto = self._open_url_android(url)
            else:
                import webbrowser
                abierto = webbrowser.open(url)
        except Exception as e:
            logger.error(f"Error al abrir navegador: {e}", exc_info=True)
            abierto = False

        if abierto:
            logger.debug(f"Link de vinculación abierto en {self.platform_name}")
        else:
            logger.error("No se pudo abrir el navegador con %s", url)
            self.linkError = ("No se pudo abrir el navegador. Escaneá el QR "
                              f"o entrá a:\n{url}")
        return abierto
    
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


