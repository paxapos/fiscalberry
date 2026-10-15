# coding=utf-8
"""
Tests del publicador de errores no bloqueante (Fase 6). Requiere paho.
"""

import time

import pytest

pytest.importorskip("paho")

from fiscalberry.common.rabbitmq import error_publisher as ep


def _wait_until(predicate, timeout=3.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_publish_error_is_non_blocking_and_never_raises():
    # No debe lanzar aunque no haya broker; retorna de inmediato.
    t0 = time.time()
    ep.publish_error("TEST_TYPE", "mensaje", context={"password": "x"})
    assert (time.time() - t0) < 0.5


def test_sanitize_masks_sensitive_keys():
    s = ep._sanitize_context({"password": "p", "ok": 1, "n": {"token": "t"}})
    assert s["password"] == "***"
    assert s["ok"] == 1
    assert s["n"]["token"] == "***"


def test_dispatcher_delivers_and_rate_limits(monkeypatch):
    delivered = []

    class FakePublisher:
        def publish_error(self, error_type, error_message, context=None, exception=None):
            delivered.append((error_type, error_message, context))

    monkeypatch.setattr(ep, "get_error_publisher", lambda: FakePublisher())

    d = ep._ErrorDispatcher()
    d.MIN_INTERVAL = 60.0  # ventana amplia para probar rate-limit

    # Dos del mismo tipo seguidos: solo uno pasa (rate-limit).
    d.submit({"error_type": "A", "error_message": "1", "context": None})
    d.submit({"error_type": "A", "error_message": "2", "context": None})
    # Uno de otro tipo: pasa.
    d.submit({"error_type": "B", "error_message": "3", "context": None})

    assert _wait_until(lambda: len(delivered) == 2)
    types = sorted(t for t, _, _ in delivered)
    assert types == ["A", "B"]


def test_dispatcher_drops_when_full_without_blocking(monkeypatch):
    # Nunca debe bloquear aunque el worker no drene (cola llena -> descarta viejo).
    monkeypatch.setattr(ep, "get_error_publisher", lambda: None)  # worker fallará suave
    d = ep._ErrorDispatcher()
    d.MIN_INTERVAL = 0.0  # sin rate-limit para este test
    t0 = time.time()
    for i in range(500):
        d.submit({"error_type": f"T{i}", "error_message": str(i), "context": None})
    assert (time.time() - t0) < 2.0  # no se colgó


def test_client_id_incluye_tenant_y_uuid(monkeypatch):
    # El client id MQTT debe llevar tenant Y uuid del dispositivo: solo el
    # tenant colisiona cuando un comercio tiene mas de un fiscalberry y el
    # broker entra en un loop de desconexiones mutuas por duplicate id.
    captured = {}

    class FakeClient:
        def username_pw_set(self, *a, **k):
            pass

        def connect(self, *a, **k):
            raise ConnectionRefusedError("sin broker en el test")

        def loop_start(self):
            pass

    def fake_make_client(client_id, clean_session=True, protocol=None):
        captured["client_id"] = client_id
        return FakeClient()

    monkeypatch.setattr(ep.mqtt_compat, "make_client", fake_make_client)

    pub = ep.ErrorPublisher()
    pub.tenant = "comercio_demo"
    pub.uuid = "11111111-2222-4333-8444-555555555555"
    pub.error_topic = "fiscalberry/errors/comercio_demo/11111111-2222-4333-8444-555555555555"
    pub.connect()

    assert captured["client_id"] == (
        "fiscalberry-errors-comercio_demo-11111111-2222-4333-8444-555555555555"
    )


# ---------------------------------------------------------------------------
# core#473: un cliente MQTT por proceso, nunca dos vivos con el mismo client id
# ---------------------------------------------------------------------------
# Si connect() crea un cliente nuevo sin frenar el anterior, el viejo sigue con
# su loop de red y paho lo reconecta solo con el MISMO client id: el broker
# patea a uno, el otro se reconecta, y así para siempre (tormenta de
# "duplicate id" desde una sola IP). Cada patada además pone _connected=False,
# el próximo error crea otro cliente más y la tormenta crece sin techo.

BROKER = {"host": "broker.test", "port": 1883, "user": "u", "password": "p"}


class LoopClient:
    """Cliente paho falso que registra si su loop de red está corriendo."""

    def __init__(self, client_id, conecta=True):
        self.client_id = client_id
        self.conecta = conecta
        self.loop_corriendo = False
        self.desconectado = False
        self.on_connect = self.on_disconnect = self.on_publish = None

    def username_pw_set(self, *a, **k):
        pass

    def reconnect_delay_set(self, *a, **k):
        pass

    def connect(self, *a, **k):
        pass

    def connect_async(self, *a, **k):
        pass

    def loop_start(self):
        self.loop_corriendo = True
        if self.conecta:
            self.on_connect(self, None, {}, 0)

    def loop_stop(self):
        self.loop_corriendo = False

    def disconnect(self):
        self.desconectado = True

    def publish(self, *a, **k):
        class R:
            mid = 1
        return R()


def _publisher(monkeypatch, conecta=True):
    creados = []

    def fake_make_client(client_id, clean_session=True, protocol=None):
        c = LoopClient(client_id, conecta=conecta)
        creados.append(c)
        return c

    monkeypatch.setattr(ep.mqtt_compat, "make_client", fake_make_client)
    pub = ep.ErrorPublisher()
    pub.tenant = "comercio_demo"
    pub.uuid = "11111111-2222-4333-8444-555555555555"
    pub.error_topic = "fiscalberry/errors/comercio_demo/11111111-2222-4333-8444-555555555555"
    pub._get_mqtt_config = lambda: dict(BROKER)
    return pub, creados


def _vivos(creados):
    return [c for c in creados if c.loop_corriendo]


def test_tras_una_desconexion_no_queda_un_segundo_cliente_vivo(monkeypatch):
    pub, creados = _publisher(monkeypatch)
    assert pub.connect() is True

    # El broker patea al cliente (corte de red, duplicate id, etc.).
    pub._on_disconnect(creados[0], None, 7)
    assert pub._connected is False

    # Llega otro error mientras paho se está reconectando solo.
    pub.publish_error("PRINTER_ERROR", "impresora offline")

    assert len(_vivos(creados)) == 1


def test_timeout_de_conexion_no_deja_un_cliente_huerfano(monkeypatch):
    monkeypatch.setattr(ep.ErrorPublisher, "CONNECT_TIMEOUT", 0.1, raising=False)
    pub, creados = _publisher(monkeypatch, conecta=False)

    assert pub.connect() is False  # el broker no contestó a tiempo
    pub.connect()  # el próximo error vuelve a intentar

    assert len(_vivos(creados)) == 1


def test_si_cambia_el_broker_frena_el_cliente_viejo_antes_de_crear_otro(monkeypatch):
    pub, creados = _publisher(monkeypatch)
    pub.connect()
    pub._on_disconnect(creados[0], None, 7)

    # Llegaron credenciales nuevas (rediscover / cambio de broker).
    pub._get_mqtt_config = lambda: dict(BROKER, password="otra")
    assert pub.connect() is True

    assert len(creados) == 2
    assert creados[0].loop_corriendo is False and creados[0].desconectado is True
    assert _vivos(creados) == [creados[1]]


def test_eventos_de_un_cliente_viejo_no_pisan_el_estado_del_actual(monkeypatch):
    pub, creados = _publisher(monkeypatch)
    pub.connect()
    pub._get_mqtt_config = lambda: dict(BROKER, password="otra")
    pub._on_disconnect(creados[0], None, 7)
    pub.connect()
    assert pub._connected is True

    # Un callback tardío del cliente anterior no debe marcar desconectado al nuevo.
    pub._on_disconnect(creados[0], None, 7)
    assert pub._connected is True
