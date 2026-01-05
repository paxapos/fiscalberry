from fiscalberry.common.fiscalberry_logger import getLogger
import sys
import os
import signal
import socketio
from fiscalberry.common.fiscalberry_sio import FiscalberrySio
from fiscalberry.common.discover import send_discover_in_thread
from fiscalberry.common.Configberry import Configberry
import time
import threading

logger = getLogger("ServiceController")

class ServiceController:
    """
    Controla el inicio y detención del servicio socketio de Fiscalberry.
    El servicio controla 2 cosas: por un lado el socketio queda como daemond, el discover se ejecuta y finaliza.
    SocketIO sirve para mensajear y recibir mensajes de la aplicación cliente. Sirve para comunicarse y enviarle comandos de managment bidireccionales.
        Por ejemplo un event importante que tiene el servicio de SocketIO es inicializar el cliente de RabbitMQ (RabbitMQProcessHandler)
    El discover:  es un request donde envia informacion como la IP, el UUID y datos de las impresoras instaladas en esta PC. Envia el request y el thread deberia finalizar.
    
    El servicio de socketio queda corriendo en segundo plano y se encarga de recibir mensajes y enviar respuestas.
    """
    
    sio: FiscalberrySio = None
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceController, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def reset_singleton(cls):
        """
        Resetea el estado del singleton para permitir reinicialización.
        
        CRÍTICO para Android: Cuando la app se cierra y reabre, el proceso Python
        puede sobrevivir y el singleton mantiene estado previo (_stop_event.set(),
        initialized=True) causando que el servicio no reinicie.
        
        Debe llamarse desde FiscalberryApp.__init__() en Android.
        """
        if cls._instance:
            # Limpiar el evento de stop para permitir reinicio
            if hasattr(cls._instance, '_stop_event'):
                cls._instance._stop_event.clear()
            # Marcar como no inicializado para forzar re-init completo
            if hasattr(cls._instance, 'initialized'):
                cls._instance.initialized = False
            # Limpiar referencias a threads muertos
            if hasattr(cls._instance, 'socketio_thread'):
                cls._instance.socketio_thread = None
            if hasattr(cls._instance, 'discover_thread'):
                cls._instance.discover_thread = None
        # Resetear también el singleton de FiscalberrySio
        try:
            from fiscalberry.common.fiscalberry_sio import FiscalberrySio
            FiscalberrySio.reset_singleton()
        except Exception:
            pass
    
    def __init__(self):
        if hasattr(self, 'initialized'):
            return
            
        self.initialized = True
        self.socketio_thread = None
        self.discover_thread = None
        
        try:
            self.configberry = Configberry()
            self._stop_event = threading.Event()
            self.initial_retries = 0

            sio_host = self.configberry.get("SERVIDOR", "sio_host")
            if not sio_host:
                logger.error("sio_host no configurado")
                os._exit(1)

            uuidval = self.configberry.get("SERVIDOR", "uuid", fallback="")
            
        except Exception as e:
            logger.error(f"Error ServiceController init: {e}")
            raise
        if not uuidval:
            logger.error("UUID no encontrado")
            os._exit(1)

        logger.info(f"ServiceController: {sio_host} uuid={uuidval[:8]}...")
        self.sio = FiscalberrySio(sio_host, uuidval)
        
        # Configurar manejo de señales
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Configura los manejadores de señales para detener limpiamente."""
        # Guardar las referencias a los manejadores originales
        self._original_sigint_handler = signal.getsignal(signal.SIGINT)
        self._original_sigterm_handler = signal.getsignal(signal.SIGTERM)
        
        # Registrar nuestros manejadores
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, sig, frame):
        """Manejador de señales para cierre graceful."""
        logger.debug(f"Recibida señal {signal.Signals(sig).name}. Deteniendo servicios...")
        
        # Solicitar detención limpia (sin sys.exit)
        self._stop_services_only()
        
        # Terminar inmediatamente después de la limpieza
        logger.debug("Terminando aplicación...")
        os._exit(0)  # Terminar de forma inmediata y definitiva

    def is_service_running(self):
        """Verifica si el servicio ya está en ejecución."""
        # Verifica si el hilo está activo
        if self.socketio_thread and self.socketio_thread.is_alive():
            return True
        return False

    def isSocketIORunning(self):
        """
        Verifica si el hilo de SIO está en ejecución.
        """
        return self.sio.isSioRunning()
    
    def isRabbitRunning(self):
        """
        Verifica si el hilo de RabbitMQ está en ejecución.
        """
        return self.sio.isRabbitMQRunning()
    
    def toggle_service(self):
        """Alterna el estado del servicio."""
        if self.is_service_running():
            logger.debug("Deteniendo el servicio...")
            return self.stop()
        else:
            logger.debug("Iniciando el servicio...")
            return self.start()

    def _run_sio_instance(self):
        """Ejecuta una instancia/conexión de FiscalberrySio y ESPERA a que termine."""
        sio_internal_thread = None # Para almacenar el hilo devuelto por sio.start()
        try:
            # sio.start() crea y arranca el hilo interno (_run) y lo devuelve
            sio_internal_thread = self.sio.start()

            # ¡IMPORTANTE! Esperar a que el hilo interno de SIO termine.
            if sio_internal_thread and isinstance(sio_internal_thread, threading.Thread):
                # Usar join con timeout para poder verificar periódicamente si hay una solicitud de stop
                while sio_internal_thread.is_alive() and not self._stop_event.is_set():
                    sio_internal_thread.join(timeout=1.0)
                
                if self._stop_event.is_set() and sio_internal_thread.is_alive():
                    logger.debug("Stop event detected during SIO internal thread join")
                else:
                    logger.debug("FiscalberrySio internal thread finished.")
            else:
                logger.warning("self.start() did not return a running thread to wait for.")

        except socketio.exceptions.ConnectionError as e:
            logger.error(f"SIO Connection Error in instance thread: {e}", exc_info=False)
        except Exception as e:
            logger.error(f"Unhandled Exception in SIO instance thread: {e}", exc_info=True)
        finally:
            logger.debug("Exiting _run_sio_instance.")

    def start(self):
        """Inicia y mantiene vivo el proceso de conexión SIO."""
        logger.info("Iniciando Fiscalberry SIO Service Loop")
        self._stop_event.clear()
        self.initial_retries = 0

        if self._stop_event.is_set():
            logger.debug("Stop requested during initial check.")
            return

        # Enviar el discover al servidor
        self.discover_thread = send_discover_in_thread()
        self.discover_thread.start()

        # Bucle principal de reconexión
        while not self._stop_event.is_set():
            self.socketio_thread = threading.Thread(
                target=self._run_sio_instance,
                daemon=True
            )
            logger.debug("SocketIO thread start.")
            self.socketio_thread.start()
            
            while self.socketio_thread.is_alive() and not self._stop_event.is_set():
                self.socketio_thread.join(timeout=1.0)
            
            logger.debug("SocketIO thread finished or stop requested.")

            if self._stop_event.is_set():
                logger.debug("Stop event received. Exiting SIO loop.")
                break

            logger.warning("SIO thread terminated. Reconnecting in 5 seconds...")
            time.sleep(5)

        logger.debug("Fiscalberry SIO Service Loop finished.")

    def _is_gui_mode(self):
        """Detecta si la aplicación está ejecutándose en modo GUI."""
        try:
            # Intentar importar kivy para verificar si está disponible
            import kivy
            from kivy.app import App
            # Si hay una app de Kivy ejecutándose, estamos en modo GUI
            return App.get_running_app() is not None
        except ImportError:
            # Si no se puede importar Kivy, definitivamente es CLI
            return False
        except:
            # Si hay cualquier otro error, asumir CLI
            return False

    def stop(self):
        """Detiene el bucle de servicios y la instancia SIO."""
        # Detectar automáticamente si estamos en modo GUI o CLI
        if self._is_gui_mode():
            return self.stop_for_gui()
        else:
            return self.stop_for_cli()

    def stop_for_cli(self):
        """Detiene el bucle de servicios específicamente para modo CLI."""
        logger.debug("Requesting SIO services stop (CLI mode)...")
        self._stop_event.set()
        
        self.sio.stop()
        
        if self.socketio_thread and self.socketio_thread.is_alive():
            # Dar tiempo para que termine limpiamente
            for _ in range(5):  # Esperar hasta 5 segundos en incrementos de 1 segundo
                if not self.socketio_thread.is_alive():
                    break
                time.sleep(1)
                    
            if self.socketio_thread.is_alive():
                logger.warning("SIO thread did not stop within the timeout period.")
        else:
            logger.debug("SIO thread already stopped or not started.")
                
        # Detener el hilo de discover si está activo
        if self.discover_thread and self.discover_thread.is_alive():
            logger.debug("Stopping discover thread...")
            self.discover_thread.join(timeout=2)
            if self.discover_thread.is_alive():
                logger.warning("Discover thread did not stop within the timeout period.")
        else:
            logger.debug("Discover thread already stopped or not started.")
                
        logger.debug("SIO services stopped (CLI mode).")
        
        # Para CLI usamos sys.exit(0)
        sys.exit(0)
        
        return True  # Esta línea ya no se ejecutará, pero la dejamos por compatibilidad

    def stop_for_gui(self):
        """Detiene el bucle de servicios específicamente para modo GUI."""
        logger.debug("Requesting SIO services stop (GUI mode)...")
        self._stop_event.set()
        
        self.sio.stop()
        
        if self.socketio_thread and self.socketio_thread.is_alive():
            # Dar tiempo para que termine limpiamente
            for _ in range(5):  # Esperar hasta 5 segundos en incrementos de 1 segundo
                if not self.socketio_thread.is_alive():
                    break
                time.sleep(1)
                    
            if self.socketio_thread.is_alive():
                logger.warning("SIO thread did not stop within the timeout period.")
        else:
            logger.debug("SIO thread already stopped or not started.")
                
        # Detener el hilo de discover si está activo
        if self.discover_thread and self.discover_thread.is_alive():
            logger.debug("Stopping discover thread...")
            self.discover_thread.join(timeout=2)
            if self.discover_thread.is_alive():
                logger.warning("Discover thread did not stop within the timeout period.")
        else:
            logger.debug("Discover thread already stopped or not started.")
                
        logger.debug("SIO services stopped (GUI mode).")
        
        # Para GUI NO intentar cerrar Kivy desde aquí - evitar recursión
        # La aplicación GUI debe manejar su propio cierre desde on_stop()
        return True

    def _stop_services_only(self):
        """Detiene solo los servicios sin llamar a sys.exit() - para uso interno."""
        logger.debug("Requesting SIO services stop...")
        self._stop_event.set()
        
        self.sio.stop()
        
        if self.socketio_thread and self.socketio_thread.is_alive():
            # Dar tiempo para que termine limpiamente
            for _ in range(5):  # Esperar hasta 5 segundos en incrementos de 1 segundo
                if not self.socketio_thread.is_alive():
                    break
                time.sleep(1)
                    
            if self.socketio_thread.is_alive():
                logger.warning("SIO thread did not stop within the timeout period.")
        else:
            logger.debug("SIO thread already stopped or not started.")
                
        # Detener el hilo de discover si está activo
        if self.discover_thread and self.discover_thread.is_alive():
            logger.debug("Stopping discover thread...")
            self.discover_thread.join(timeout=2)
            if self.discover_thread.is_alive():
                logger.warning("Discover thread did not stop within the timeout period.")
        else:
            logger.debug("Discover thread already stopped or not started.")
                
        logger.debug("SIO services stopped.")
        
        return True



