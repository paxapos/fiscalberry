# coding=utf-8
"""
TLS de MQTT informado por el servidor en `start_rabbit`.

Lo que se fija:
  - si el servidor manda `use_tls` (con `mqtt_port` y, opcional, la CA en PEM
    en `ca_cert`), el cliente MQTT se conecta con TLS, verificando el
    certificado, sin tocar config.ini;
  - si el servidor no dice nada, todo queda como hoy: sin TLS, puerto 1883;
  - si se pidió TLS y no se puede aplicar, no se conecta: nunca se cae a texto
    plano en silencio;
  - el heartbeat y el ErrorPublisher usan el mismo TLS que el consumer.
"""

import logging
import ssl
import threading

import pytest

pytest.importorskip("paho")
certifi = pytest.importorskip("certifi")

from fiscalberry.common import heartbeat as hb
from fiscalberry.common.rabbitmq import consumer as consumer_mod
from fiscalberry.common.rabbitmq import error_publisher as ep
from fiscalberry.common.rabbitmq import mqtt_compat
from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler


def _una_ca_pem():
    """Un certificado de CA real (el primero de certifi), sin red."""
    with open(certifi.where(), encoding="ascii") as fh:
        texto = fh.read()
    fin = "-----END CERTIFICATE-----"
    inicio = texto.index("-----BEGIN CERTIFICATE-----")
    return texto[inicio:texto.index(fin, inicio) + len(fin)] + "\n"


class ConfigFalso:
    def __init__(self, datos):
        self.datos = {s: dict(v) for s, v in datos.items()}

    def get(self, seccion, clave, fallback=None):
        return self.datos.get(seccion, {}).get(clave, fallback)

    def set(self, seccion, valores):
        self.datos.setdefault(seccion, {}).update(valores)


class ClienteMqttFalso:
    """Anota cómo se configuró el cliente y a dónde se conectó."""

    def __init__(self):
        self.tls_set_llamadas = []
        self.contexto = None
        self.inseguro = []
        self.conexiones = []

    def username_pw_set(self, *a, **k):
        pass

    def tls_set(self, ca_certs=None, **kwargs):
        self.tls_set_llamadas.append(ca_certs)

    def tls_set_context(self, context=None):
        self.contexto = context

    def tls_insecure_set(self, valor):
        self.inseguro.append(valor)

    def reconnect_delay_set(self, **k):
        pass

    def connect(self, host, port, keepalive=60):
        self.conexiones.append((host, int(port)))

    connect_async = connect

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    @property
    def con_tls(self):
        return bool(self.tls_set_llamadas) or self.contexto is not None


@pytest.fixture
def clientes(monkeypatch):
    creados = []

    def fake_make_client(client_id, clean_session=True, protocol=None):
        c = ClienteMqttFalso()
        creados.append(c)
        return c

    monkeypatch.setattr(mqtt_compat, "make_client", fake_make_client)
    return creados


@pytest.fixture
def handler(monkeypatch):
    RabbitMQProcessHandler._instance = None
    RabbitMQProcessHandler._initialized = False
    h = RabbitMQProcessHandler.__new__(RabbitMQProcessHandler)
    h._thread = None
    h._current_consumer = None
    h._consumer_lock = threading.Lock()
    h._stop_event = threading.Event()
    h.active_credentials = None
    h.config = ConfigFalso({
        "RabbitMq": {"vhost": "/", "queue": "cola"},
        "SERVIDOR": {"uuid": "uuid-del-equipo"},
    })
    monkeypatch.setattr(h, "stop", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(h, "_check_network_connectivity", lambda host, port: True)
    for var in ("FISCALBERRY_MQTT_HOST", "FISCALBERRY_MQTT_PORT"):
        monkeypatch.delenv(var, raising=False)

    # Una vuelta del loop del consumer: conecta y avisa que terminó.
    def start_una_vez(consumer):
        try:
            consumer.connect()
        finally:
            h._stop_event.set()

    monkeypatch.setattr(consumer_mod.RabbitMQConsumer, "start", start_una_vez)
    yield h
    RabbitMQProcessHandler._instance = None
    RabbitMQProcessHandler._initialized = False


def _start_rabbit(handler, **rabbit):
    """Lo que hace el evento start_rabbit, y arranca el consumer de verdad."""
    cfg = {"RabbitMq": dict({
        "host": "broker.ejemplo.com",
        "port": "5672",
        "user": "fiscalberry",
        "password": "secreto",
        "queue": "cola",
    }, **rabbit)}
    handler.configure_and_restart(cfg, None)
    RabbitMQProcessHandler.start(handler, None)
    handler._thread.join(timeout=5)
    assert not handler._thread.is_alive()


def test_start_rabbit_con_tls_puerto_y_ca_conecta_con_tls(handler, clientes):
    ca = _una_ca_pem()

    _start_rabbit(handler, use_tls=True, mqtt_port="8883", ca_cert=ca)

    cliente = clientes[-1]
    assert cliente.conexiones == [("broker.ejemplo.com", 8883)]
    ctx = cliente.contexto
    assert isinstance(ctx, ssl.SSLContext), "no se configuró TLS con la CA del servidor"
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert len(ctx.get_ca_certs()) == 1
    assert cliente.inseguro == []


def test_use_tls_como_texto_y_sin_ca_usa_las_ca_del_sistema(handler, clientes):
    _start_rabbit(handler, use_tls="true")

    cliente = clientes[-1]
    assert cliente.tls_set_llamadas == [None]
    # Sin mqtt_port, el default con TLS.
    assert cliente.conexiones == [("broker.ejemplo.com", 8883)]


def test_sin_campos_de_tls_conecta_igual_que_hoy(handler, clientes):
    _start_rabbit(handler, mqtt_port="1883")

    cliente = clientes[-1]
    assert not cliente.con_tls
    assert cliente.conexiones == [("broker.ejemplo.com", 1883)]


def test_el_servidor_no_puede_apagar_el_tls_local(handler, clientes):
    handler.config.datos["RabbitMq"]["use_tls"] = "true"

    _start_rabbit(handler, use_tls=False, mqtt_port="8883")

    assert clientes[-1].con_tls


def test_tls_pedido_que_no_se_puede_aplicar_no_cae_a_texto_plano(handler, clientes, caplog):
    with caplog.at_level(logging.ERROR):
        _start_rabbit(handler, use_tls=True, mqtt_port="8883", ca_cert="esto no es un PEM")

    assert all(c.conexiones == [] for c in clientes), "se conectó sin TLS"
    assert any(r.levelno >= logging.ERROR and "TLS" in r.getMessage()
               for r in caplog.records)


def test_el_heartbeat_usa_el_tls_informado(clientes):
    class Handler:
        def get_active_rabbitmq_credentials(self):
            return {"host": "broker.ejemplo.com", "port": "8883", "user": "u",
                    "password": "p", "use_tls": True, "ca_data": None}

    latido = hb.HeartbeatPublisher(configberry=ConfigFalso({}), process_handler=Handler())
    assert latido._connect()

    assert clientes[-1].con_tls
    assert clientes[-1].conexiones == [("broker.ejemplo.com", 8883)]


def test_el_error_publisher_usa_el_tls_informado(monkeypatch, clientes):
    monkeypatch.setattr(RabbitMQProcessHandler, "_instance", None)
    monkeypatch.setattr(RabbitMQProcessHandler, "get_active_rabbitmq_credentials",
                        lambda self: {"host": "broker.ejemplo.com", "port": "8883",
                                      "user": "u", "password": "p",
                                      "use_tls": True, "ca_data": None})
    pub = ep.ErrorPublisher()
    pub.tenant = "comercio_demo"
    pub.uuid = "uuid-del-equipo"
    pub.error_topic = "fiscalberry/errors/comercio_demo/uuid-del-equipo"
    monkeypatch.setattr(pub, "CONNECT_TIMEOUT", 0)

    pub.connect()

    assert clientes[-1].con_tls
    assert clientes[-1].conexiones == [("broker.ejemplo.com", 8883)]
