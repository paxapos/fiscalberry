# coding=utf-8
"""
Tests de la identidad del dispositivo.

El UUID identifica al equipo ante Paxapos y es el topic MQTT: si cambia, hay que
re-vincular el comercio y la cola vieja queda huérfana. Lo que se fija acá:

  - derivado de ANDROID_ID ⇒ reinstalar la app devuelve el MISMO UUID;
  - un uuid ya existente en config.ini NUNCA se pisa.
"""

import uuid

import pytest

from fiscalberry.common import device_uuid


def test_mismo_android_id_mismo_uuid(monkeypatch):
    """Reinstalar no puede cambiar la identidad del dispositivo."""
    monkeypatch.setattr(device_uuid, "get_android_id", lambda: "a1b2c3d4e5f60718")

    primero = device_uuid.generate_device_uuid()
    segundo = device_uuid.generate_device_uuid()

    assert primero == segundo
    uuid.UUID(primero)  # tiene que ser un UUID válido: se usa como topic MQTT


def test_distintos_dispositivos_distinto_uuid(monkeypatch):
    monkeypatch.setattr(device_uuid, "get_android_id", lambda: "1111111111111111")
    uno = device_uuid.generate_device_uuid()

    monkeypatch.setattr(device_uuid, "get_android_id", lambda: "2222222222222222")
    otro = device_uuid.generate_device_uuid()

    assert uno != otro


def test_sin_android_id_cae_en_aleatorio(monkeypatch):
    """En escritorio no hay identificador estable: aleatorio, pero válido."""
    monkeypatch.setattr(device_uuid, "get_android_id", lambda: None)

    generado = device_uuid.generate_device_uuid()
    uuid.UUID(generado)
    assert generado != device_uuid.generate_device_uuid()


def test_get_android_id_no_lanza_en_escritorio():
    assert device_uuid.get_android_id() is None


def test_reset_no_pisa_un_uuid_existente(monkeypatch, tmp_path):
    """
    Regresión: un reset por config corrupta regeneraba el uuid al azar y el
    dispositivo pasaba a ser otro para el servidor.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    from fiscalberry.common.Configberry import Configberry

    Configberry._instance = None
    config = Configberry()

    original = config.get("SERVIDOR", "uuid")
    assert original

    config.resetConfigFile()

    assert config.get("SERVIDOR", "uuid") == original
    Configberry._instance = None
