# coding=utf-8
"""
Tests del heartbeat local (Fase 7). Requiere paho (heartbeat importa mqtt_compat).
"""

import pytest

pytest.importorskip("paho")

from fiscalberry.common import heartbeat as hb


class FakeConfig:
    def __init__(self, values=None):
        self._v = values or {}

    def get(self, section, key, fallback=None):
        return self._v.get((section, key), fallback)


def test_build_payload_has_expected_fields_and_no_secrets():
    p = hb.build_heartbeat_payload(
        uuid="uuid-1", tenant="demo", mqtt_connected=True,
        pending=3, failed=1, version="3.1.0", ts=12345)
    assert p == {
        "uuid": "uuid-1", "tenant": "demo", "mqtt_connected": True,
        "pending": 3, "failed": 1, "version": "3.1.0", "ts": 12345,
    }
    # Sin claves sensibles.
    assert not any(k in p for k in ("password", "user", "token", "credentials"))


def test_is_enabled_reads_config():
    off = hb.HeartbeatPublisher(configberry=FakeConfig())
    assert off.is_enabled() is False

    on = hb.HeartbeatPublisher(
        configberry=FakeConfig({("Heartbeat", "enabled"): "true"}))
    assert on.is_enabled() is True


def test_interval_has_minimum():
    p = hb.HeartbeatPublisher(
        configberry=FakeConfig({("Heartbeat", "interval"): "1"}))
    assert p.interval() == hb.HeartbeatPublisher.MIN_INTERVAL

    p2 = hb.HeartbeatPublisher(
        configberry=FakeConfig({("Heartbeat", "interval"): "120"}))
    assert p2.interval() == 120.0


def test_start_returns_false_when_disabled():
    p = hb.HeartbeatPublisher(configberry=FakeConfig())
    assert p.start() is False
    assert p._thread is None


def test_current_payload_uses_spooler_counts():
    class FakeSpooler:
        def pending_count(self):
            return 7

        def failed_count(self):
            return 2

    cfg = FakeConfig({
        ("Paxaprinter", "tenant"): "demo",
        ("SERVIDOR", "uuid"): "uuid-9",
    })
    p = hb.HeartbeatPublisher(
        configberry=cfg, process_handler=None,
        spooler_getter=lambda: FakeSpooler())
    payload = p.current_payload()
    assert payload["pending"] == 7
    assert payload["failed"] == 2
    assert payload["tenant"] == "demo"
    assert payload["uuid"] == "uuid-9"
    assert payload["mqtt_connected"] is False
