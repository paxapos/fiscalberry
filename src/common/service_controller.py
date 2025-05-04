
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
    """
    Controla el inicio y detención del servicio socketio de Fiscalberry.
    El servicio controla 2 cosas: por un lado el socketio queda como daemond, el discover se ejecuta y finaliza.
    SocketIO sirve para mensajear y recibir mensajes de la aplicación cliente. Sirve para comunicarse y enviarle comandos de managment bidireccionales.
        Por ejemplo un event importante que tiene el servicio de SocketIO es inicializar el cliente de RabbitMQ (RabbitMQProcessHandler)
    El discover:  es un request donde envia informacion como la IP, el UUID y datos de las impresoras instaladas en esta PC. Envia el request y el thread deberia finalizar.
    
    El servicio de socketio queda corriendo en segundo plano y se encarga de recibir mensajes y enviar respuestas.
    """
    
    sio: FiscalberrySio = None
    
    def __init__(self):
        self.socketio_thread = None
        self.discover_thread = None
        self.configberry = Configberry()
        self._stop_event = threading.Event() # Evento para detener limpiamente
        self.initial_retries = 0 # Contador para chequeo inicial de UUID

        sio_host = self.configberry.get("SERVIDOR", "sio_host")
        if not sio_host:
            logger.error("sio_host no configurado. Abortando.")
            # raise RuntimeError("sio_host configuration missing.")
            os._exit(1) # O manejar el error

        # --- Bucle de chequeo inicial de UUID ---
        uuidval = self.configberry.get("SERVIDOR", "uuid", fallback="")
        if not uuidval:
            logger.error(f"UUID NO encontrado en config file: {uuidval}")
            # raise RuntimeError("sio_host configuration missing.")
            os._exit(1) # O manejar el error

        self.sio = FiscalberrySio(sio_host, uuidval)


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
            logger.info("Deteniendo el servicio...")
            return self.stop()
        else:
            logger.info("Iniciando el servicio...")
            return self.start()


    def _run_sio_instance(self):
        """Ejecuta una instancia/conexión de FiscalberrySio y ESPERA a que termine."""
        sio_internal_thread = None # Para almacenar el hilo devuelto por sio.start()
        try:
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
        
        

        if self._stop_event.is_set():
            logger.info("Stop requested during initial UUID check.")
            return # Salir si se pidió detener


         # Enviar el discover al servidor la pruimera vez
        self.discover_thread = send_discover_in_thread()
        self.discover_thread.start()
        

        # --- Bucle principal de reconexión ---
        while not self._stop_event.is_set():
            
            # Creamos un hilo que ejecutará _run_sio_instance
            # _run_sio_instance internamente llama a sio.start() que es bloqueante
            self.socketio_thread = threading.Thread(
                target=self._run_sio_instance,
                daemon=True # Daemon para que no bloquee la salida si el principal muere
            )
            logger.info("* * * * * SocketIO thread start.")
            self.socketio_thread.start()
            self.socketio_thread.join() # Espera a que _run_sio_instance termine
            logger.info("* * * * * SocketIO thread finished.")

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
        logger.info("# # # Requesting SIO services stop...")
        self._stop_event.set()
        
        self.sio.stop()
        
        if self.socketio_thread and self.socketio_thread.is_alive():
            self.socketio_thread.join(timeout=5)
            if self.socketio_thread.is_alive():
                logger.warning("SIO thread did not stop within the timeout period of 5 seconds.")
        else:
            logger.info("SIO thread already stopped or not started.")
        # Detener el hilo de discover si está activo
        if self.discover_thread and self.discover_thread.is_alive():
            logger.info("Stopping discover thread...")
            self.discover_thread.join(timeout=5)
            if self.discover_thread.is_alive():
                logger.warning("Discover thread did not stop within the timeout period of 5 seconds.")
        else:
            logger.info("Discover thread already stopped or not started.")
            
        logger.info("SIO services stopped.")
        
    
                
        return True

        

