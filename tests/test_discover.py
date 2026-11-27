# coding=utf-8
"""
Tests del discover: el POST de registro debe incluir la version del cliente
(el backend la persiste para decidir capacidades, ej. trabajos 'printRaw').
"""

import json

import pytest

pytest.importorskip("requests")

import fiscalberry.common.discover as discover  # noqa: E402
from fiscalberry.version import VERSION  # noqa: E402


class FakeParser:
    def __init__(self, values):
        self._values = values

    def get(self, section, key, fallback=""):
        return self._values.get((section, key), fallback)


class FakeConfigberry:
    def __init__(self, uuid="test-uuid-1234", host="https://server.test"):
        self.config = FakeParser({
            ("SERVIDOR", "uuid"): uuid,
            ("SERVIDOR", "sio_host"): host,
        })

    def getJSON(self):
        return {"SERVIDOR": {"uuid": "test-uuid-1234"}}

    def get_ssl_verify(self):
        return True


class FakeResponse:
    status_code = 200
    text = ""


def test_discover_payload_includes_version(monkeypatch):
    sent = {}

    def fake_post(url, headers=None, data=None, timeout=None, verify=None):
        sent["url"] = url
        sent["body"] = json.loads(data)
        return FakeResponse()

    monkeypatch.setattr(discover, "configberry", FakeConfigberry())
    monkeypatch.setattr(discover, "listar_impresoras", lambda: ["POS-80"])
    monkeypatch.setattr(discover.requests, "post", fake_post)

    assert discover.send_discover() is True
    assert sent["url"] == "https://server.test/discover.json"
    assert sent["body"]["uuid"] == "test-uuid-1234"
    # La version viaja top-level junto al uuid (no dentro de raw_data).
    assert sent["body"]["version"] == VERSION
    raw = json.loads(sent["body"]["raw_data"])
    assert raw["installed_printers"] == ["POS-80"]


def test_discover_without_uuid_does_not_post(monkeypatch):
    called = []
    monkeypatch.setattr(discover, "configberry", FakeConfigberry(uuid=""))
    monkeypatch.setattr(discover.requests, "post", lambda *a, **k: called.append(1))

    assert discover.send_discover() is False
    assert not called


class EventoQueNoCorta:
    """stop_event que anota cada espera y vuelve enseguida."""

    def __init__(self):
        self.esperas = []

    def is_set(self):
        return False

    def wait(self, segundos):
        self.esperas.append(segundos)
        return False


def test_hasta_registrar_reintenta_con_espera_creciente(monkeypatch):
    respuestas = iter([False, RuntimeError("sin red"), False, False, False, False, True])

    def falso():
        r = next(respuestas)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(discover, "send_discover", falso)
    evento = EventoQueNoCorta()
    avisos = []

    assert discover.send_discover_hasta_registrar(evento, lambda i, e: avisos.append((i, e))) is True
    assert evento.esperas == [2, 4, 8, 16, 30, 30]
    assert avisos == [(1, 2), (2, 4), (3, 8), (4, 16), (5, 30), (6, 30)]


def test_hasta_registrar_para_con_el_stop_event(monkeypatch):
    import threading

    llamadas = []
    monkeypatch.setattr(discover, "send_discover", lambda: llamadas.append(1) or False)
    stop = threading.Event()

    assert discover.send_discover_hasta_registrar(stop, lambda i, e: stop.set()) is False
    assert llamadas == [1]

    assert discover.send_discover_hasta_registrar(stop) is False
    assert llamadas == [1]
