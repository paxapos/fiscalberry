# coding=utf-8
"""
Reasignar el dispositivo a otro comercio desde la plataforma.

El servidor manda los datos del comercio en cada (re)conexión de SocketIO
(evento start_rabbit). Antes solo se escribían en config.ini si estaban VACÍOS,
así que el primer tenant quedaba grabado para siempre: cambiarlo en la
plataforma no tenía ningún efecto en el dispositivo, que seguía publicando sus
errores con el tenant viejo y mostrando el comercio equivocado en pantalla.

Lo que estos tests fijan:
  - tenant/alias/site_name y queue se ACTUALIZAN cuando el servidor manda otro valor;
  - host/port/vhost NO se pisan: ahí un override local es legítimo.
"""

import pytest

from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler


class ConfigFalso:
    """Config en memoria con la misma interfaz que usa el handler."""

    def __init__(self, datos):
        self.datos = {s: dict(v) for s, v in datos.items()}

    def get(self, seccion, clave, fallback=None):
        return self.datos.get(seccion, {}).get(clave, fallback)

    def set(self, seccion, valores):
        self.datos.setdefault(seccion, {}).update(valores)


@pytest.fixture
def handler(monkeypatch):
    """Handler con config en memoria y sin arrancar hilos de red."""
    RabbitMQProcessHandler._instance = None
    RabbitMQProcessHandler._initialized = False

    h = RabbitMQProcessHandler.__new__(RabbitMQProcessHandler)
    h._thread = None
    h._current_consumer = None
    h.active_credentials = None
    h.config = ConfigFalso({
        "RabbitMq": {"host": "broker.viejo", "port": "1883", "vhost": "/", "queue": "cola-vieja"},
        "Paxaprinter": {"tenant": "paxapoga_cangas", "alias": "Ale celu", "site_name": "Cangas"},
        "SERVIDOR": {"uuid": "uuid-del-equipo"},
    })
    monkeypatch.setattr(h, "stop", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(h, "start", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(h, "_update_active_credentials", lambda *a, **k: None, raising=False)
    yield h
    RabbitMQProcessHandler._instance = None
    RabbitMQProcessHandler._initialized = False


def _config_del_servidor(tenant="alejandro", queue="cola-nueva"):
    return {
        "RabbitMq": {"host": "broker.nuevo", "user": "u", "password": "p", "queue": queue},
        "Paxaprinter": {"tenant": tenant, "alias": "Ale celu", "site_name": "Alejandro"},
    }


def test_el_tenant_se_actualiza_desde_el_servidor(handler):
    handler.configure_and_restart(_config_del_servidor(), None)

    assert handler.config.get("Paxaprinter", "tenant") == "alejandro"
    assert handler.config.get("Paxaprinter", "site_name") == "Alejandro"


def test_la_cola_se_actualiza_desde_el_servidor(handler):
    handler.configure_and_restart(_config_del_servidor(), None)

    assert handler.config.get("RabbitMq", "queue") == "cola-nueva"


def test_el_host_local_no_se_pisa(handler):
    """Un broker configurado a mano es una decisión de quien instala el equipo."""
    handler.configure_and_restart(_config_del_servidor(), None)

    assert handler.config.get("RabbitMq", "host") == "broker.viejo"
    assert handler.config.get("RabbitMq", "port") == "1883"


def test_sin_cambios_no_toca_nada(handler):
    """Si el servidor manda lo mismo, no hay reescritura."""
    mismo = {
        "RabbitMq": {"queue": "cola-vieja", "user": "u", "password": "p"},
        "Paxaprinter": {"tenant": "paxapoga_cangas", "alias": "Ale celu", "site_name": "Cangas"},
    }
    handler.configure_and_restart(mismo, None)

    assert handler.config.get("Paxaprinter", "tenant") == "paxapoga_cangas"
    assert handler.config.get("RabbitMq", "queue") == "cola-vieja"


def test_valores_vacios_del_servidor_no_borran_lo_que_hay(handler):
    vacio = {"RabbitMq": {"user": "u", "password": "p"}, "Paxaprinter": {}}
    handler.configure_and_restart(vacio, None)

    assert handler.config.get("Paxaprinter", "tenant") == "paxapoga_cangas"
    assert handler.config.get("RabbitMq", "queue") == "cola-vieja"
