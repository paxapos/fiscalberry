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
    pub.tenant = "palote_pastas"
    pub.uuid = "b7b6c00f-ae49-48b0-a6c2-8876c97f27d2"
    pub.error_topic = "fiscalberry/errors/palote_pastas/b7b6c00f-ae49-48b0-a6c2-8876c97f27d2"
    pub.connect()

    assert captured["client_id"] == (
        "fiscalberry-errors-palote_pastas-b7b6c00f-ae49-48b0-a6c2-8876c97f27d2"
    )
