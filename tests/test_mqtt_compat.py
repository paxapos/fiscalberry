# coding=utf-8
"""
Tests de mqtt_compat (Fases 5 y 9). Requiere paho instalado.
"""

import pytest

pytest.importorskip("paho")

from fiscalberry.common.rabbitmq import mqtt_compat


class FakeConfig:
    """Config mínima con .get(section, key, fallback) sobre un dict plano."""

    def __init__(self, values=None):
        self._v = values or {}

    def get(self, section, key, fallback=None):
        return self._v.get((section, key), fallback)


class FakeClient:
    def __init__(self):
        self.tls_set_calls = []
        self.tls_insecure_calls = []

    def tls_set(self, ca_certs=None, **kwargs):
        self.tls_set_calls.append(ca_certs)

    def tls_insecure_set(self, value):
        self.tls_insecure_calls.append(value)


def test_make_client_returns_client():
    c = mqtt_compat.make_client(client_id="test-client", clean_session=True)
    assert c is not None


def test_rc_is_success_int():
    assert mqtt_compat.rc_is_success(0) is True
    assert mqtt_compat.rc_is_success(1) is False


def test_rc_is_success_reasoncode_like():
    class RC:
        def __init__(self, fail):
            self.is_failure = fail
    assert mqtt_compat.rc_is_success(RC(False)) is True
    assert mqtt_compat.rc_is_success(RC(True)) is False


def test_read_tls_config_defaults_no_tls():
    cfg = FakeConfig()
    tls = mqtt_compat.read_mqtt_tls_config(cfg)
    assert tls["use_tls"] is False
    assert tls["port"] == 1883
    assert tls["ca_cert"] is None
    assert tls["tls_insecure"] is False


def test_read_tls_config_tls_defaults_8883():
    cfg = FakeConfig({("RabbitMq", "use_tls"): "true"})
    tls = mqtt_compat.read_mqtt_tls_config(cfg)
    assert tls["use_tls"] is True
    assert tls["port"] == 8883


def test_read_tls_config_explicit_port_respected():
    cfg = FakeConfig({("RabbitMq", "use_tls"): "true", ("RabbitMq", "port"): "9999"})
    tls = mqtt_compat.read_mqtt_tls_config(cfg)
    assert tls["port"] == 9999


def test_apply_tls_disabled_does_nothing():
    client = FakeClient()
    applied = mqtt_compat.apply_tls(client, {"use_tls": False})
    assert applied is False
    assert client.tls_set_calls == []


def test_apply_tls_enabled_calls_tls_set():
    client = FakeClient()
    applied = mqtt_compat.apply_tls(client, {
        "use_tls": True, "ca_cert": "/tmp/ca.pem", "tls_insecure": True})
    assert applied is True
    assert client.tls_set_calls == ["/tmp/ca.pem"]
    assert client.tls_insecure_calls == [True]


# ---------------------------------------------------------------------------
# core#473: nunca dos clientes vivos con el mismo client id en un proceso
# ---------------------------------------------------------------------------

def _puerto_cerrado():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _cliente_con_loop(client_id, port):
    """Cliente paho real con su loop corriendo (reintenta contra un puerto cerrado)."""
    c = mqtt_compat.make_client(client_id=client_id, clean_session=True)
    c.connect_async("127.0.0.1", port, keepalive=60)
    c.loop_start()
    return c, c._thread


def test_make_client_frena_el_cliente_previo_con_el_mismo_id():
    port = _puerto_cerrado()
    viejo, hilo_viejo = _cliente_con_loop("fiscalberry-test-dup-473", port)
    assert hilo_viejo.is_alive()

    nuevo, hilo_nuevo = _cliente_con_loop("fiscalberry-test-dup-473", port)
    try:
        hilo_viejo.join(timeout=5)
        assert not hilo_viejo.is_alive()
        assert hilo_nuevo.is_alive()
    finally:
        nuevo.loop_stop()


def test_make_client_no_toca_clientes_con_otro_id():
    port = _puerto_cerrado()
    a, hilo_a = _cliente_con_loop("fiscalberry-test-a-473", port)
    b, hilo_b = _cliente_con_loop("fiscalberry-test-b-473", port)
    try:
        assert hilo_a.is_alive() and hilo_b.is_alive()
    finally:
        a.loop_stop()
        b.loop_stop()
