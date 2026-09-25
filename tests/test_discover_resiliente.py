# coding=utf-8
"""
Registrar el dispositivo no puede depender de detectar impresoras.

Caso real: en el celular la vinculación moría con ":: Paxaprinter no
encontrada". El servidor tenía razón — nunca había recibido el discover, así
que no existía ninguna Paxaprinter con ese uuid.

La causa: `listar_impresoras()` se llamaba FUERA del try, y en Android escanea
USB y Bluetooth, que dependen de permisos que en la primera vinculación el
usuario todavía no otorgó. Si eso fallaba, el discover ni se intentaba.

Y es al revés de como tiene que ser: en la primera vinculación **no hay**
impresoras configuradas. Que la lista venga vacía es lo esperado, no un motivo
para no registrar el equipo.
"""

import pytest

from fiscalberry.common import discover


class RespuestaOk:
    status_code = 200
    text = "ok"


@pytest.fixture
def config(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from fiscalberry.common.Configberry import Configberry
    Configberry._instance = None
    cfg = Configberry()
    monkeypatch.setattr(discover, "configberry", cfg)
    yield cfg
    Configberry._instance = None


def test_se_registra_aunque_falle_la_deteccion_de_impresoras(config, monkeypatch):
    """Lo importante es que el dispositivo quede registrado."""
    enviados = {}

    def explota():
        raise RuntimeError("BluetoothAdapter: permiso denegado")

    monkeypatch.setattr(discover, "listar_impresoras", explota)
    monkeypatch.setattr(discover.requests, "post",
                        lambda url, **kw: (enviados.update(url=url, **kw), RespuestaOk())[1])

    assert discover.send_discover() is True
    assert "/discover.json" in enviados["url"]


def test_manda_lista_vacia_de_impresoras_si_no_pudo_detectarlas(config, monkeypatch):
    import json

    capturado = {}

    monkeypatch.setattr(discover, "listar_impresoras",
                        lambda: (_ for _ in ()).throw(OSError("sin permisos")))
    monkeypatch.setattr(discover.requests, "post",
                        lambda url, **kw: (capturado.update(kw), RespuestaOk())[1])

    discover.send_discover()

    enviado = json.loads(capturado["data"])
    assert json.loads(enviado["raw_data"])["installed_printers"] == []


def test_sin_impresoras_es_un_caso_normal(config, monkeypatch):
    """La primera vinculación siempre ocurre sin impresoras configuradas."""
    monkeypatch.setattr(discover, "listar_impresoras", lambda: [])
    monkeypatch.setattr(discover.requests, "post", lambda url, **kw: RespuestaOk())

    assert discover.send_discover() is True


def test_sin_uuid_no_se_registra(config, monkeypatch):
    """Registrar sin identidad no tendría sentido: el servidor no sabría quién es."""
    monkeypatch.setattr(discover.configberry.config, "get",
                        lambda *a, **kw: "")

    assert discover.send_discover() is False
