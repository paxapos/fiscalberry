
import subprocess
from common.fiscalberry_logger import getLogger
import os
from common.fiscalberry_sio import FiscalberrySio
from common.discover import send_discover_in_thread
from common.Configberry import Configberry
import time
import threading
from common.fiscalberry_logger import getLogger
logger = getLogger()

class ServiceController:
    """Controla el inicio y detención del servicio."""
    
    sio: FiscalberrySio = None
    
    def __init__(self):
        self.socketio_thread = None
        self.discover_thread = None
        self.configberry = Configberry()
        self._stop_event = threading.Event() # Evento para detener limpiamente
        self.initial_retries = 0 # Contador para chequeo inicial de UUID


    def is_service_running(self):
        """Verifica si el servicio ya está en ejecución."""
        # Verifica si el hilo está activo
        if self.socketio_thread and self.socketio_thread.is_alive():
            return True
        return False
        
    def toggle_service(self):
        """Alterna el estado del servicio."""
        if self.is_service_running():
            logger.info("Deteniendo el servicio...")
            self.stop()
        else:
            logger.info("Iniciando el servicio...")
            self.start()


    def _run_sio_instance(self, sio_host, uuid):
        """Ejecuta una instancia/conexión de FiscalberrySio y ESPERA a que termine."""
        sio_internal_thread = None # Para almacenar el hilo devuelto por sio.start()
        try:
            # FiscalberrySio es singleton, esto obtiene/crea la instancia
            self.sio = FiscalberrySio(sio_host, uuid)

            # sio.start() crea y arranca el hilo interno (_run) y lo devuelve
            sio_internal_thread = self.sio.start()

            # ¡IMPORTANTE! Esperar a que el hilo interno de SIO termine.
            if sio_internal_thread and isinstance(sio_internal_thread, threading.Thread):
                sio_internal_thread.join() # Bloquea aquí hasta que _run finalice
                logger.info("FiscalberrySio internal thread finished.")
            else:
                # Esto puede pasar si self.start() no inició un nuevo hilo (quizás ya estaba corriendo)
                # O si la lógica de start() cambió. Añadir manejo si es necesario.
                logger.warning("self.start() did not return a running thread to wait for.")

        except socketio.exceptions.ConnectionError as e:
            logger.error(f"SIO Connection Error in instance thread: {e}", exc_info=False) # No mostrar traceback completo para errores de conexión comunes
        except Exception as e:
            logger.error(f"Unhandled Exception in SIO instance thread: {e}", exc_info=True)
        finally:
            # Este log ahora indica que _run_sio_instance (y el join interno) ha terminado
            logger.info("Exiting _run_sio_instance.")


    def start(self):
        """Inicia y mantiene vivo el proceso de conexión SIO."""
        logger.info("Iniciando Fiscalberry SIO Service Loop")
        self._stop_event.clear()
        self.initial_retries = 0

        # --- Bucle de chequeo inicial de UUID ---
        uuidval = None
        while not self._stop_event.is_set():
            uuidval = self.configberry.get("SERVIDOR", "uuid", fallback="")
            if uuidval:
                logger.info(f"UUID encontrado: {uuidval}")
                break # Tenemos UUID, continuar

            self.initial_retries += 1
            if self.initial_retries > 5:
                logger.error("UUID no configurado tras 5 reintentos. Abortando.")
                # Considera lanzar una excepción en lugar de os._exit
                # raise RuntimeError("UUID configuration missing after multiple retries.")
                os._exit(1) # O manejar el error de otra forma

            logger.warning(f"UUID no encontrado. Reintentando en 5s... (Intento {self.initial_retries}/5)")
            time.sleep(5)

        if self._stop_event.is_set():
            logger.info("Stop requested during initial UUID check.")
            return # Salir si se pidió detener

        sio_host = self.configberry.get("SERVIDOR", "sio_host")
        if not sio_host:
            logger.error("sio_host no configurado. Abortando.")
            # raise RuntimeError("sio_host configuration missing.")
            os._exit(1) # O manejar el error

        # --- Bucle principal de reconexión ---
        while not self._stop_event.is_set():
            logger.info(f"Iniciando intento de conexión SIO a {sio_host}...")
            
            # Enviar el discover al servidor
            self.discover_thread = send_discover_in_thread()
            logger.info("* * * * * enviando discover")
            self.discover_thread.start()
            self.discover_thread.join()
            logger.info("* * * * * Discover enviado")
            
            # Creamos un hilo que ejecutará _run_sio_instance
            # _run_sio_instance internamente llama a sio.start() que es bloqueante
            self.socketio_thread = threading.Thread(
                target=self._run_sio_instance,
                args=(sio_host, uuidval),
                daemon=True # Daemon para que no bloquee la salida si el principal muere
            )
            self.socketio_thread.start()
            self.socketio_thread.join() # Espera a que _run_sio_instance termine

            # Si el hilo terminó, verificamos si fue por una señal de stop
            if self._stop_event.is_set():
                logger.info("Stop event received. Exiting SIO loop.")
                break # Salir del bucle while

            # Si no fue por stop, asumimos desconexión/error y reintentamos
            logger.warning("SIO thread terminated. Reconnecting in 5 seconds...")
            time.sleep(5)

        logger.info("Fiscalberry SIO Service Loop finished.")

    def stop(self):
        """Detiene el bucle de servicios y la instancia SIO."""
        logger.info("Requesting SIO services stop...")
        self._stop_event.set()

        # Intentar detener la instancia SIO si existe y está inicializada
        try:
            # Acceder a la instancia singleton (puede requerir ajustar __new__/__init__)
            # Si __init__ no hace nada si ya está inicializado, esto es seguro:
            sio_instance = FiscalberrySio(None, None) # Args dummy si __init__ los necesita
            if hasattr(sio_instance, '_initialized') and sio_instance._initialized:
                logger.info("Stopping active FiscalberrySio instance...")
                sio_instance.stop()
            else:
                logger.info("FiscalberrySio instance not initialized or found.")
        except Exception as e:
            logger.error(f"Error trying to stop FiscalberrySio instance: {e}", exc_info=True)

        # Esperar un poco a que el hilo principal termine si está en join/sleep
        if self.socketio_thread and self.socketio_thread.is_alive():
            self.socketio_thread.join(timeout=1.0)
        logger.info("SIO services stop requested.")

