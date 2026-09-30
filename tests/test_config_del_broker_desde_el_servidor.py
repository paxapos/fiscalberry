# coding=utf-8
"""
De dónde salen host y puerto del broker MQTT.

Antes mandaba config.ini: si el archivo traía un `port`, se respetaba y el valor
del servidor se descartaba. Eso dejó un local sin imprimir durante semanas con
un puerto viejo clavado en el archivo, y el síntoma del lado del broker eran
handshakes MQTT contra el puerto AMQP (`bad_header`).

Lo que estos tests fijan:
  - el host y el puerto los decide el SERVIDOR (evento start_rabbit);
  - el puerto viaja en la clave NUEVA `mqtt_port`; la vieja `port` es el puerto
    AMQP del backend y no se mira nunca;
  - contra un servidor viejo que no manda `mqtt_port` se cae al default local
    (1883/8883 según use_tls), que es el comportamiento que hoy mantiene viva a
    la flota;
  - nada de esto se persiste en config.ini: vive en memoria, como user/password;
  - queda un escape hatch por variable de entorno, ruidoso y efímero, para
    cuando el servidor manda mal.
"""

import logging
import threading

import pytest

from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler


class ConfigFalso:
    """Config en memoria con la misma interfaz que usa el handler."""

    def __init__(self, datos):
        self.datos = {s: dict(v) for s, v in datos.items()}
        self.escrituras = []

    def get(self, seccion, clave, fallback=None):
        return self.datos.get(seccion, {}).get(clave, fallback)

    def set(self, seccion, valores):
        self.escrituras.append((seccion, dict(valores)))
        self.datos.setdefault(seccion, {}).update(valores)


@pytest.fixture
def handler(monkeypatch):
    """Handler con config en memoria, sin hilos de red y registrando credenciales."""
    RabbitMQProcessHandler._instance = None
    RabbitMQProcessHandler._initialized = False

    h = RabbitMQProcessHandler.__new__(RabbitMQProcessHandler)
    h._thread = None
    h._current_consumer = None
    h._consumer_lock = threading.Lock()
    h._stop_event = threading.Event()
    h.active_credentials = None
    h.config = ConfigFalso({
        # Un equipo ya instalado: arrastra host/port viejos en el archivo.
        "RabbitMq": {"host": "broker.viejo", "port": "5672", "vhost": "/", "queue": "cola-vieja"},
        "Paxaprinter": {"tenant": "paxapoga_cangas", "alias": "Ale celu", "site_name": "Cangas"},
        "SERVIDOR": {"uuid": "uuid-del-equipo"},
    })
    monkeypatch.setattr(h, "stop", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(h, "start", lambda *a, **k: None, raising=False)
    # Sin monkeypatch: queremos ver qué queda en memoria.
    for var in ("FISCALBERRY_MQTT_HOST", "FISCALBERRY_MQTT_PORT"):
        monkeypatch.delenv(var, raising=False)
    yield h
    RabbitMQProcessHandler._instance = None
    RabbitMQProcessHandler._initialized = False


def _del_servidor(**extra):
    cfg = {
        "RabbitMq": {
            "host": "broker.ejemplo.com",
            # `port` es el puerto AMQP del backend: el cliente NO debe mirarlo.
            "port": "5672",
            "mqtt_port": "1883",
            "user": "fiscalberry",
            "password": "secreto",
            "queue": "cola-vieja",
        },
        "Paxaprinter": {"tenant": "paxapoga_cangas", "alias": "Ale celu", "site_name": "Cangas"},
    }
    cfg["RabbitMq"].update(extra)
    return cfg


def test_el_host_lo_manda_el_servidor(handler):
    """El host del archivo ya no gana: manda la nube."""
    handler.configure_and_restart(_del_servidor(), None)

    assert handler.active_credentials["host"] == "broker.ejemplo.com"


def test_el_puerto_sale_de_mqtt_port_y_no_del_config(handler):
    """Un puerto viejo en config.ini no puede secuestrar la conexión."""
    handler.configure_and_restart(_del_servidor(), None)

    assert handler.active_credentials["port"] == "1883"


def test_nunca_se_usa_el_puerto_amqp_que_manda_el_servidor(handler):
    """`port` es el puerto AMQP; usarlo da bad_header contra el broker."""
    handler.configure_and_restart(_del_servidor(), None)

    assert handler.active_credentials["port"] != "5672"


def test_servidor_viejo_sin_mqtt_port_cae_al_default_local(handler):
    """Compat: la flota instalada sigue andando aunque el backend no se actualice."""
    cfg = _del_servidor()
    del cfg["RabbitMq"]["mqtt_port"]

    handler.configure_and_restart(cfg, None)

    assert handler.active_credentials["port"] == "1883"


def test_servidor_viejo_con_tls_cae_a_8883(handler):
    handler.config.datos["RabbitMq"]["use_tls"] = "true"
    cfg = _del_servidor()
    del cfg["RabbitMq"]["mqtt_port"]

    handler.configure_and_restart(cfg, None)

    assert handler.active_credentials["port"] == "8883"


def test_host_y_puerto_no_se_persisten(handler):
    """
    Lo que no está en disco no se puede leer ni quedar viejo.

    Se parte de una instalación NUEVA (sin host/port en el archivo), que es
    justo el caso donde antes se rellenaba y quedaba grabado para siempre.
    """
    handler.config.datos["RabbitMq"] = {"queue": "cola-vieja"}

    handler.configure_and_restart(_del_servidor(), None)

    escrito = {}
    for seccion, valores in handler.config.escrituras:
        if seccion == "RabbitMq":
            escrito.update(valores)

    assert "host" not in escrito
    assert "port" not in escrito
    assert "vhost" not in escrito


def test_la_password_nunca_toca_el_disco(handler):
    handler.configure_and_restart(_del_servidor(), None)

    for _seccion, valores in handler.config.escrituras:
        assert "password" not in valores
        assert "user" not in valores


def test_la_env_var_pisa_al_servidor(handler, monkeypatch):
    """Escape hatch para cuando la nube manda mal: deliberado y efímero."""
    monkeypatch.setenv("FISCALBERRY_MQTT_PORT", "8883")
    monkeypatch.setenv("FISCALBERRY_MQTT_HOST", "broker.dev.local")

    handler.configure_and_restart(_del_servidor(), None)

    assert handler.active_credentials["port"] == "8883"
    assert handler.active_credentials["host"] == "broker.dev.local"


def test_el_override_por_env_grita_en_el_log(handler, monkeypatch, caplog):
    """Un override silencioso es el modo de falla a evitar; tiene que verse siempre."""
    monkeypatch.setenv("FISCALBERRY_MQTT_PORT", "9999")

    with caplog.at_level(logging.WARNING):
        handler.configure_and_restart(_del_servidor(), None)

    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("FISCALBERRY_MQTT_PORT" in m for m in avisos), avisos


def test_si_el_servidor_no_manda_host_se_usa_el_del_config(handler, caplog):
    """Fallback legacy, pero anunciado."""
    cfg = _del_servidor(host="")

    with caplog.at_level(logging.WARNING):
        handler.configure_and_restart(cfg, None)

    assert handler.active_credentials["host"] == "broker.viejo"
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_start_toma_host_y_puerto_de_memoria(handler, monkeypatch):
    """
    start() leía host/port de config.ini. Si dejamos de persistirlos y no se
    arregla, el consumidor arranca contra None y no conecta nunca.
    """
    capturado = {}

    class ThreadFalso:
        def __init__(self, target=None, args=(), **kwargs):
            capturado["args"] = args

        def start(self):
            pass

        def is_alive(self):
            return False

    monkeypatch.setattr(
        "fiscalberry.common.rabbitmq.process_handler.threading.Thread", ThreadFalso
    )
    # Se invoca el método de la clase para saltear el stub de instancia del fixture.
    handler.active_credentials = {
        "host": "broker.ejemplo.com",
        "port": "1883",
        "user": "fiscalberry",
        "password": "secreto",
        "vhost": "/",
    }
    handler._stop_event = __import__("threading").Event()

    RabbitMQProcessHandler.start(handler, None)

    host, port = capturado["args"][0], capturado["args"][1]
    assert host == "broker.ejemplo.com"
    assert port == "1883"
