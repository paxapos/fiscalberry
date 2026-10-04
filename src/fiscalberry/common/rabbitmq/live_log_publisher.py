"""
Publicador MQTT propio de los live logs.

Los live logs viajan por una conexion MQTT SEPARADA de la de la cola de
impresion, igual que los errores (ErrorPublisher). Motivo: si el broker no le
permite al usuario publicar en `fiscalberry/logs/...` (permiso de topic que no
esta en las definitions), RabbitMQ CIERRA la conexion MQTT del cliente. Si los
logs salieran por la conexion del consumer, abrir los logs en vivo desde el
panel dejaria al comercio sin imprimir. Con una conexion propia, lo peor que
pasa es que los logs no llegan.

La conexion se abre recien con la primera sesion de logs y se cierra cuando se
cierra la ultima (LiveLogStreamManager llama a `close()` al quedar ocioso).
"""

import logging
import threading
import time

import paho.mqtt.client as mqtt

from fiscalberry.common.rabbitmq import mqtt_compat

# Nombre bajo `fiscalberry.live_logs`: el handler de captura ignora este logger,
# asi un error de publicacion no genera otra linea a publicar (lazo infinito).
logger = logging.getLogger("fiscalberry.live_logs.publisher")

CONNECT_TIMEOUT_SECONDS = 5.0
MQTT_PORT_DEFAULT = 1883


def _active_credentials():
    """Credenciales del broker que mando el servidor (solo en memoria)."""
    from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler

    return RabbitMQProcessHandler().get_active_rabbitmq_credentials()


def _tls_config():
    from fiscalberry.common.Configberry import Configberry

    return mqtt_compat.read_mqtt_tls_config(Configberry())


class LiveLogMqttPublisher:
    """Cliente MQTT perezoso y dedicado a los live logs de un dispositivo."""

    def __init__(
        self,
        uuid,
        credentials_provider=_active_credentials,
        tls_config_provider=_tls_config,
        client_factory=mqtt_compat.make_client,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
    ):
        self.uuid = uuid
        self._credentials_provider = credentials_provider
        self._tls_config_provider = tls_config_provider
        self._client_factory = client_factory
        self._connect_timeout = connect_timeout
        self._client = None
        self._connected = threading.Event()
        self._lock = threading.Lock()

    # -- API publica ---------------------------------------------------------
    def publish(self, topic, payload, qos=0):
        """Publica un batch. Devuelve False si no hay conexion (se cuenta como perdido).

        Puede bloquear hasta `connect_timeout` la primera vez: lo llama el hilo
        de LiveLogStreamManager, nunca el de Socket.IO ni el de impresion.
        """
        client = self._ensure_client()
        if client is None:
            return False
        if not self._connected.wait(self._connect_timeout):
            return False
        try:
            result = client.publish(topic, payload, qos=qos)
        except Exception as exc:  # noqa: BLE001 - un log perdido no debe romper nada
            logger.debug("Live logs: fallo publicando: %s", exc)
            return False
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def close(self):
        """Cierra la conexion (sin sesiones activas no tiene sentido mantenerla)."""
        with self._lock:
            client = self._client
            self._client = None
            self._connected.clear()
        if client is None:
            return
        try:
            client.disconnect()
            client.loop_stop()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Live logs: error cerrando MQTT: %s", exc)

    def is_connected(self):
        return self._connected.is_set()

    # -- Conexion ------------------------------------------------------------
    def _ensure_client(self):
        with self._lock:
            if self._client is not None:
                return self._client
            credentials = self._credentials_provider() or {}
            host = credentials.get("host")
            if not host:
                logger.debug("Live logs: sin credenciales del broker todavia")
                return None
            try:
                port = int(credentials.get("port") or MQTT_PORT_DEFAULT)
            except (TypeError, ValueError):
                port = MQTT_PORT_DEFAULT

            # client id propio: no puede coincidir con el del consumer (el broker
            # patearia la conexion de impresion) ni con el de errores.
            client = self._client_factory(
                client_id="fiscalberry-logs-{}".format(self.uuid),
                clean_session=True,
                protocol=mqtt.MQTTv311,
            )
            client.username_pw_set(credentials.get("user", ""), credentials.get("password", ""))
            try:
                mqtt_compat.apply_tls(client, self._tls_config_provider())
            except Exception as exc:  # noqa: BLE001
                logger.debug("Live logs: no se pudo aplicar TLS: %s", exc)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            # Reintentos rapidos pero acotados: si el broker corta por permisos,
            # no hay que martillarlo mientras dure la sesion.
            client.reconnect_delay_set(min_delay=1, max_delay=30)
            try:
                client.connect_async(host, port, keepalive=30)
                client.loop_start()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Live logs: no se pudo conectar a %s:%s: %s", host, port, exc)
                return None
            self._client = client
            return client

    def _on_connect(self, client, userdata, flags, rc):
        if mqtt_compat.rc_is_success(rc):
            self._connected.set()
        else:
            self._connected.clear()
            logger.debug("Live logs: conexion MQTT rechazada (rc=%s)", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected.clear()
        if rc != 0:
            logger.debug("Live logs: desconexion MQTT inesperada (rc=%s)", rc)


_publisher = None
_publisher_lock = threading.Lock()


def get_live_log_publisher(uuid):
    """Singleton por proceso; se recrea si cambia el uuid del dispositivo."""
    global _publisher
    with _publisher_lock:
        if _publisher is None or _publisher.uuid != uuid:
            if _publisher is not None:
                _publisher.close()
            _publisher = LiveLogMqttPublisher(uuid)
        return _publisher
