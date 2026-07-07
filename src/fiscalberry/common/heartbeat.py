# coding=utf-8
"""
Heartbeat local opcional (Fase 7).

Publica periódicamente un latido a un topic MQTT para que el backend/broker pueda
saber que este Fiscalberry está vivo y con qué estado de cola. Es totalmente
opt-in y no requiere cambios en el backend: si nadie escucha el topic, no pasa nada.

Configuración (sección [Heartbeat] de config.ini):
  - enabled  = true/false   (default false)
  - interval = 60           (segundos; default 60, mínimo 5)

Topic:  fiscalberry/heartbeat/{tenant}/{uuid}   (QoS 0, para no cargar el broker)

Payload (sin secretos):
  { uuid, tenant, mqtt_connected, pending, failed, version, ts }
"""

import json
import threading
import time

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.rabbitmq import mqtt_compat

logger = getLogger("MQTT.Heartbeat")

try:
    from fiscalberry.version import VERSION as _FB_VERSION
except Exception:  # pragma: no cover
    _FB_VERSION = "unknown"


def _truthy(value):
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def build_heartbeat_payload(uuid, tenant, mqtt_connected, pending, failed,
                            version=_FB_VERSION, ts=None):
    """Construye el payload del heartbeat (función pura, testeable sin MQTT)."""
    return {
        "uuid": uuid,
        "tenant": tenant,
        "mqtt_connected": bool(mqtt_connected),
        "pending": int(pending),
        "failed": int(failed),
        "version": version,
        "ts": ts if ts is not None else int(time.time()),
    }


class HeartbeatPublisher:
    """Publicador de heartbeat en un thread daemon. Opt-in y resiliente."""

    DEFAULT_INTERVAL = 60.0
    MIN_INTERVAL = 5.0

    def __init__(self, configberry=None, process_handler=None, spooler_getter=None):
        self.config = configberry or Configberry()
        self._process_handler = process_handler
        self._spooler_getter = spooler_getter
        self._client = None
        self._thread = None
        self._stop = threading.Event()

    # -- configuración -------------------------------------------------------
    def is_enabled(self):
        return _truthy(self.config.get("Heartbeat", "enabled", fallback="false"))

    def interval(self):
        try:
            val = float(self.config.get("Heartbeat", "interval", fallback=self.DEFAULT_INTERVAL))
        except (TypeError, ValueError):
            val = self.DEFAULT_INTERVAL
        return max(self.MIN_INTERVAL, val)

    def _tenant(self):
        return self.config.get("Paxaprinter", "tenant", fallback="") or ""

    def _uuid(self):
        return self.config.get("SERVIDOR", "uuid", fallback="") or ""

    def _topic(self):
        return f"fiscalberry/heartbeat/{self._tenant()}/{self._uuid()}"

    # -- estado --------------------------------------------------------------
    def _mqtt_connected(self):
        ph = self._process_handler
        try:
            return bool(ph.is_running()) if ph else False
        except Exception:
            return False

    def _spooler_counts(self):
        try:
            sp = self._spooler_getter() if self._spooler_getter else None
            if sp is None:
                return 0, 0
            return sp.pending_count(), sp.failed_count()
        except Exception:
            return 0, 0

    def current_payload(self):
        pending, failed = self._spooler_counts()
        return build_heartbeat_payload(
            uuid=self._uuid(), tenant=self._tenant(),
            mqtt_connected=self._mqtt_connected(),
            pending=pending, failed=failed)

    # -- lifecycle -----------------------------------------------------------
    def start(self):
        """Arranca el heartbeat si está habilitado por config. No bloquea."""
        if not self.is_enabled():
            logger.debug("Heartbeat deshabilitado por config ([Heartbeat] enabled=false)")
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mqtt-heartbeat", daemon=True)
        self._thread.start()
        logger.info("Heartbeat iniciado (interval=%ss, topic=%s)", self.interval(), self._topic())
        return True

    def stop(self):
        self._stop.set()
        self._disconnect()

    def _connect(self):
        creds = None
        if self._process_handler:
            try:
                creds = self._process_handler.get_active_rabbitmq_credentials()
            except Exception:
                creds = None
        if not creds:
            return False
        try:
            self._client = mqtt_compat.make_client(
                client_id=f"fiscalberry-hb-{self._uuid()}",
                clean_session=True)
            self._client.username_pw_set(creds.get("user"), creds.get("password"))
            try:
                mqtt_compat.apply_tls(self._client, mqtt_compat.read_mqtt_tls_config(self.config))
            except Exception:
                pass
            port = int(creds.get("port") or 1883)
            self._client.connect(creds.get("host"), port, keepalive=60)
            self._client.loop_start()
            return True
        except Exception as e:
            logger.debug("Heartbeat: no se pudo conectar (se reintenta): %s", e)
            self._client = None
            return False

    def _disconnect(self):
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def _run(self):
        while not self._stop.is_set():
            try:
                if self._client is None:
                    self._connect()
                if self._client is not None:
                    payload = json.dumps(self.current_payload(), ensure_ascii=False)
                    self._client.publish(self._topic(), payload, qos=0)
            except Exception as e:
                logger.debug("Heartbeat: fallo publicando (ignorado): %s", e)
                self._disconnect()
            # Espera interrumpible.
            self._stop.wait(timeout=self.interval())
        self._disconnect()
