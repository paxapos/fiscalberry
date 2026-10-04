# coding=utf-8
"""
Tests de lifecycle del consumer MQTT (Fases 4 y 10). Requiere paho.

Se mockea la capa de red (connect/cliente) para validar que:
  - stop() corta el loop de start() de inmediato (event-based, sin polling frágil).
  - el binding AMQP legacy es configurable ([RabbitMq] create_amqp_binding).
  - _on_connect interpreta el rc correctamente.
"""

import threading
import time

import pytest

pytest.importorskip("paho")

from fiscalberry.common.rabbitmq.consumer import RabbitMQConsumer


class FakeClient:
    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass


def _make_consumer():
    return RabbitMQConsumer(
        host="localhost", port=1883, user="u", password="p",
        queue_name="uuid-test")


def test_stop_interrupts_start_quickly(monkeypatch):
    c = _make_consumer()

    # Evitar red real: connect() solo instala un cliente falso y marca conectado.
    def fake_connect():
        c.client = FakeClient()
        c._connected = True

    monkeypatch.setattr(c, "connect", fake_connect)

    t = threading.Thread(target=c.start, daemon=True)
    t.start()
    time.sleep(0.2)  # dejar entrar al loop

    t0 = time.time()
    c.stop()
    t.join(timeout=3)
    assert not t.is_alive(), "start() no terminó tras stop()"
    assert (time.time() - t0) < 2.0, "stop() tardó demasiado (esperado <2s)"


def test_amqp_binding_enabled_reads_config(monkeypatch):
    c = _make_consumer()
    monkeypatch.setattr(c._configberry, "get", lambda s, k, fallback=None: "false")
    assert c._amqp_binding_enabled() is False
    monkeypatch.setattr(c._configberry, "get", lambda s, k, fallback=None: "true")
    assert c._amqp_binding_enabled() is True


def test_on_subscribe_skips_binding_when_disabled(monkeypatch):
    c = _make_consumer()
    monkeypatch.setattr(c, "_amqp_binding_enabled", lambda: False)
    called = {"n": 0}
    monkeypatch.setattr(c, "_create_queue_binding", lambda: called.__setitem__("n", called["n"] + 1))
    c._on_subscribe(None, None, 1, (1,))
    assert c._subscribed is True
    assert called["n"] == 0  # no se intentó binding AMQP


def test_on_connect_sets_connected_on_success():
    c = _make_consumer()

    class Cli:
        def subscribe(self, *a, **k):
            pass

    c._on_connect(Cli(), None, {}, 0)
    assert c._connected is True

    c2 = _make_consumer()
    c2._on_connect(Cli(), None, {}, 5)  # 5 = no autorizado
    assert c2._connected is False
