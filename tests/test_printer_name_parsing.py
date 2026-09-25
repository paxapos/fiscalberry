# coding=utf-8
"""
Interpretación del printerName que manda Paxapos.

Paxapos NO manda un nombre lógico: manda el alias de la impresora, que la propia
plataforma autogenera como una querystring con la config
(`driver=Network&host=192.168.1.50&port=9100`). Así que esta función es la que
decide con qué driver se imprime.

El caso que fija este archivo: una impresora Bluetooth lleva la MAC en la
config, y la MAC tiene ":". Como el chequeo de "IP:puerto" iba ANTES que el de
"clave=valor", ese string caía en la rama equivocada y explotaba con
"too many values to unpack" — dejando a las impresoras Bluetooth sin forma de
configurarse, que son justo las únicas cuyo parámetro obligatorio contiene ":".
"""

import pytest

from fiscalberry.common.Configberry import Configberry


@pytest.fixture
def config(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    Configberry._instance = None
    yield Configberry()
    Configberry._instance = None


def test_bluetooth_con_mac_no_se_confunde_con_ip(config):
    resultado = config.get_config_for_printer(
        "driver=Bluetooth&mac_address=00:11:22:AA:BB:CC")

    assert resultado == {"driver": "Bluetooth", "mac_address": "00:11:22:AA:BB:CC"}


def test_ip_con_puerto_sigue_funcionando(config):
    resultado = config.get_config_for_printer("192.168.0.25:9100")

    assert resultado["driver"] == "Network"
    assert resultado["host"] == "192.168.0.25"
    assert resultado["port"] == "9100"


def test_querystring_de_red_como_la_arma_paxapos(config):
    """Formato exacto que autogenera Paxapos en el alias de la impresora."""
    resultado = config.get_config_for_printer(
        "driver=Network&host=192.168.1.50&port=9100")

    assert resultado == {"driver": "Network", "host": "192.168.1.50", "port": "9100"}


def test_impresora_de_prueba(config):
    assert config.get_config_for_printer("driver=Dummy") == {"driver": "Dummy"}


def test_solo_ip_sin_puerto(config):
    resultado = config.get_config_for_printer("192.168.0.25")

    assert resultado["driver"] == "Network"
    assert resultado["host"] == "192.168.0.25"
