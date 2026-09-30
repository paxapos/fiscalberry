# coding=utf-8
"""
Helpers de compatibilidad MQTT para Fiscalberry.

Centraliza:
  - Creación de `mqtt.Client` compatible con paho-mqtt 1.x y 2.x (Fase 9).
    En 2.x se fuerza `callback_api_version=VERSION1` para conservar las firmas de
    callbacks v1 que usa el resto del código, evitando una reescritura riesgosa.
  - Interpretación del "reason code" de conexión en ambas versiones.
  - Lectura de configuración TLS local y aplicación de `tls_set()` (Fase 5).

Todo es opt-in y retrocompatible: sin configuración TLS, el comportamiento es el
mismo de siempre (MQTT sin TLS en 1883).
"""

import paho.mqtt.client as mqtt

try:  # paho-mqtt >= 2.0
    from paho.mqtt.enums import CallbackAPIVersion
    _HAS_CALLBACK_API_VERSION = True
except Exception:  # paho-mqtt 1.x
    CallbackAPIVersion = None
    _HAS_CALLBACK_API_VERSION = False


def has_v2():
    """True si la versión instalada de paho expone la API de callbacks v2."""
    return _HAS_CALLBACK_API_VERSION


def make_client(client_id, clean_session=True, protocol=None):
    """Crea un `mqtt.Client` compatible con paho 1.x y 2.x.

    En 2.x se pasa `callback_api_version=CallbackAPIVersion.VERSION1` para mantener
    las firmas de callbacks v1 (on_connect(client, userdata, flags, rc), etc.).
    """
    protocol = protocol if protocol is not None else mqtt.MQTTv311
    if _HAS_CALLBACK_API_VERSION:
        return mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION1,
            client_id=client_id,
            clean_session=clean_session,
            protocol=protocol,
        )
    return mqtt.Client(
        client_id=client_id,
        clean_session=clean_session,
        protocol=protocol,
    )


def rc_is_success(rc):
    """True si el reason code/rc de conexión indica éxito.

    - paho 1.x: `rc` es int (0 == éxito).
    - paho 2.x: `rc` es un ReasonCode (tiene `.is_failure`).
    """
    if hasattr(rc, "is_failure"):
        return not rc.is_failure
    try:
        return int(rc) == 0
    except (TypeError, ValueError):
        return rc == 0


def _truthy(value):
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def read_mqtt_tls_config(configberry, section="RabbitMq"):
    """Lee la configuración TLS local desde Configberry.

    Claves soportadas en la sección (por defecto [RabbitMq]):
      - use_tls      = true/false      (default false)
      - port         = 8883 / 1883     (default 8883 si TLS, 1883 si no)
      - ca_cert      = /ruta/ca.pem    (opcional)
      - tls_insecure = true/false      (default false; solo pruebas locales)

    Devuelve un dict normalizado: {use_tls, port(int), ca_cert(str|None), tls_insecure}.
    """
    use_tls = _truthy(configberry.get(section, "use_tls", fallback="false"))

    port = configberry.get(section, "port", fallback=None)
    if not port or not str(port).strip():
        port = "8883" if use_tls else "1883"

    ca = configberry.get(section, "ca_cert", fallback="") or ""
    ca = ca.strip() or None

    tls_insecure = _truthy(configberry.get(section, "tls_insecure", fallback="false"))

    return {
        "use_tls": use_tls,
        "port": int(port),
        "ca_cert": ca,
        "tls_insecure": tls_insecure,
    }


def apply_tls(client, tls_cfg):
    """Aplica TLS al cliente MQTT si `tls_cfg['use_tls']` es verdadero.

    `tls_cfg` es el dict devuelto por `read_mqtt_tls_config()`.
    Devuelve True si se activó TLS, False si no.
    """
    if not tls_cfg or not tls_cfg.get("use_tls"):
        return False
    ca = tls_cfg.get("ca_cert") or None
    client.tls_set(ca_certs=ca)
    if tls_cfg.get("tls_insecure"):
        client.tls_insecure_set(True)
    return True
