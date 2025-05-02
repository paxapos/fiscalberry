import threading

import time
import logging
from common.Configberry import Configberry
from common.rabbitmq.consumer import RabbitMQConsumer

logger = logging.getLogger(__name__)

class RabbitMQProcessHandler:
    """Administra el hilo de RabbitMQConsumer: arranque, paro y reintentos."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._thread = None
        self._stop_event = threading.Event()
        self.config = Configberry()
        self._initialized = True


    def start(self, message_queue):
        """Arranca el consumidor en un hilo daemon (no bloqueante)."""
        if self._thread and self._thread.is_alive():
            logger.warning("RabbitMQ thread ya en ejecución.")
            return

        host = self.config.get("RabbitMq", "host")
        port = self.config.get("RabbitMq", "port")
        user = self.config.get("RabbitMq", "user")
        password = self.config.get("RabbitMq", "password")
        queue_name = self.config.get("RabbitMq", "queue")
        
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_consumer,
            args=(host, port, user, password, queue_name, message_queue),
            daemon=True
        )
        self._thread.start()
        logger.info("RabbitMQ thread iniciado.")
        
        

    def _run_consumer(self, host, port, user, password, queue_name, message_queue):
        """Loop de conexión/reconexión al servidor RabbitMQ."""
        while not self._stop_event.is_set():
            try:
                consumer = RabbitMQConsumer(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    queue_name=queue_name,
                    message_queue=message_queue
                )
                consumer.start()
                # consumer.start() sólo retorna al desconectarse o error.
            except Exception as ex:
                logger.error(f"Error en RabbitMQConsumer: {ex}", exc_info=True)
            if not self._stop_event.is_set():
                logger.warning("RabbitMQConsumer detenido; reintentando en 5 s...")
                time.sleep(5)
        logger.info("Salida del bucle de RabbitMQProcessHandler.")

    def stop(self, timeout: float = None):
        """Detiene el hilo y espera su finalización."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout)
            logger.info("RabbitMQ thread detenido.")

    def configure_and_restart(self, data: dict, message_queue):
        """
        Recibe el JSON, actualiza Configberry si cambia y reinicia el hilo.
        data debe traer keys 'RabbitMq' y 'Paxaprinter' como en tu interfaz HiDto.
        """
        rabbit_cfg = data.get('RabbitMq', {})
        # valida campos...
        host = rabbit_cfg.get('host'); port = int(rabbit_cfg.get('port', 0))
        user = rabbit_cfg.get('user'); pwd = rabbit_cfg.get('password')
        vhost = rabbit_cfg.get('vhost'); queue = rabbit_cfg.get('queue')
        # compara con lo actual
        curr = {
            "host": self.config.get("RabbitMq", "host"),
            "port": self.config.get("RabbitMq", "port"),
            "user": self.config.get("RabbitMq", "user"),
            "password": self.config.get("RabbitMq", "password"),
            "vhost": self.config.get("RabbitMq", "vhost"),
            "queue": self.config.get("RabbitMq", "queue"),
        }
        new = {"host": host, "port": port, "user": user, "password": pwd, "vhost": vhost, "queue": queue}
        if curr != new:
            self.config.set("RabbitMq", new)
            logger.info("Configuración de RabbitMQ actualizada en disk.")
            
        # compara con lo actual de Paxaprinter
        pax_cfg = data.get('Paxaprinter', {})
        alias = pax_cfg.get('alias')
        tenant = pax_cfg.get('tenant')
        site_name = pax_cfg.get('site_name')
        curr_pax = {
            "alias": self.config.get("Paxaprinter", "alias"),
            "tenant": self.config.get("Paxaprinter", "tenant"),
            "site_name": self.config.get("Paxaprinter", "site_name")
        }
        new_pax = {"alias": alias, "tenant": tenant, "site_name": site_name}
        if curr_pax != new_pax:
            self.config.set("Paxaprinter", new_pax)
            logger.info("Configuración de Paxaprinter actualizada en disk.")

        # guarda en config y reinicia hilo
        if self._thread and self._thread.is_alive():
            self.stop(timeout=5)
        self.start(message_queue)