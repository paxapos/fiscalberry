# coding=utf-8
"""
Handlers Socket.IO de los live logs (paxaprinter:logs:{start,renew,stop}).

Los comandos los manda paxa-core -> Redis -> socketio-app. Se verifica que:
  - solo se atienden comandos dirigidos al uuid propio;
  - la sesion usa el publicador MQTT DEDICADO (nunca la conexion de impresion);
  - renew/stop llegan al manager.
"""

import pytest

pytest.importorskip("socketio")

from fiscalberry.common import fiscalberry_sio as sio_module
from fiscalberry.common.fiscalberry_sio import FiscalberrySio

from test_sio_reconnect import FakeSioClient


class FakeManager:
    def __init__(self):
        self.calls = []

    def start_session(self, **kwargs):
        self.calls.append(("start", kwargs))
        return True

    def renew_session(self, session_id, expires_at=None):
        self.calls.append(("renew", session_id, expires_at))

    def stop_session(self, session_id):
        self.calls.append(("stop", session_id))

    def stop_all_sessions(self):
        self.calls.append(("stop_all",))


class FakePublisher:
    def publish(self, topic, payload, qos=0):
        return True

    def close(self):
        pass


@pytest.fixture
def sio_con_manager(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    FakeSioClient.instances = []
    monkeypatch.setattr(sio_module.socketio, "Client", FakeSioClient)
    manager = FakeManager()
    publisher = FakePublisher()
    monkeypatch.setattr(sio_module, "get_live_log_stream_manager", lambda: manager)
    monkeypatch.setattr(sio_module, "get_live_log_publisher", lambda uuid: publisher)
    FiscalberrySio.reset_singleton()
    FiscalberrySio._instance = None
    sio = FiscalberrySio("http://fake-server", "uuid-propio")
    monkeypatch.setattr(sio.config, "get", lambda *a, **k: "resto_a")
    yield sio, manager, publisher
    FiscalberrySio._instance = None


def _handler(sio, nombre):
    return sio.sio.handlers[nombre]


def test_start_abre_sesion_con_el_publicador_dedicado(sio_con_manager):
    sio, manager, publisher = sio_con_manager

    _handler(sio, "paxaprinter:logs:start")(
        {
            "uuid": "uuid-propio",
            "sessionId": "s-1",
            "expiresAt": "2026-10-04T12:00:00+00:00",
            "minLevel": "INFO",
            "snapshotLines": 50,
        }
    )

    accion, kwargs = manager.calls[0]
    assert accion == "start"
    assert kwargs["session_id"] == "s-1"
    assert kwargs["tenant"] == "resto_a"
    assert kwargs["uuid"] == "uuid-propio"
    assert kwargs["min_level"] == "INFO"
    assert kwargs["snapshot_lines"] == 50
    # Nunca la conexion de la cola de impresion (rabbit_handler).
    assert kwargs["publisher"] == publisher.publish
    assert kwargs["on_idle"] == publisher.close


@pytest.mark.parametrize(
    "evento", ["paxaprinter:logs:start", "paxaprinter:logs:renew", "paxaprinter:logs:stop"]
)
def test_ignora_comandos_para_otro_uuid(sio_con_manager, evento):
    sio, manager, _ = sio_con_manager

    _handler(sio, evento)({"uuid": "uuid-ajeno", "sessionId": "s-1"})
    _handler(sio, evento)("no-es-un-dict")

    assert manager.calls == []


def test_renew_y_stop_llegan_al_manager(sio_con_manager):
    sio, manager, _ = sio_con_manager

    _handler(sio, "paxaprinter:logs:renew")(
        {"uuid": "uuid-propio", "sessionId": "s-1", "expiresAt": "2026-10-04T12:01:00+00:00"}
    )
    _handler(sio, "paxaprinter:logs:stop")({"uuid": "uuid-propio", "sessionId": "s-1"})

    assert manager.calls == [
        ("renew", "s-1", "2026-10-04T12:01:00+00:00"),
        ("stop", "s-1"),
    ]


def test_stop_del_servicio_corta_todas_las_sesiones(sio_con_manager):
    sio, manager, _ = sio_con_manager

    sio.stop(timeout=0.1)

    assert ("stop_all",) in manager.calls
