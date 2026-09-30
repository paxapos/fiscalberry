# coding=utf-8
"""
Tests del estado del servicio compartido entre procesos.

En Android la UI y el servicio de impresión corren en procesos distintos: la UI
no puede ver los objetos del servicio y necesita leer su estado de un archivo.
Lo importante acá es que un estado viejo NO se reporte como "conectado": si el
servicio murió, la UI tiene que mostrarlo caído, no mentir.
"""

import json
import os

import pytest

from fiscalberry.common import service_status


@pytest.fixture
def status_en_tmp(monkeypatch, tmp_path):
    ruta = tmp_path / "service_status.json"
    monkeypatch.setattr(service_status, "_status_file_path", lambda: str(ruta))
    return ruta


def test_write_y_read_roundtrip(status_en_tmp):
    service_status.write_status(sio_connected=True, mqtt_connected=False)

    estado = service_status.read_status()
    assert estado is not None
    assert estado["sio_connected"] is True
    assert estado["mqtt_connected"] is False
    assert estado["pid"] == os.getpid()


def test_estado_vencido_se_ignora(status_en_tmp):
    """Un estado viejo significa servicio caído, no 'conectado'."""
    service_status.write_status(sio_connected=True, mqtt_connected=True)

    payload = json.loads(status_en_tmp.read_text())
    payload["ts"] -= service_status.STATUS_MAX_AGE_SECONDS + 60
    status_en_tmp.write_text(json.dumps(payload))

    assert service_status.read_status() is None


def test_sin_archivo_devuelve_none(status_en_tmp):
    assert service_status.read_status() is None


def test_archivo_corrupto_no_explota(status_en_tmp):
    status_en_tmp.write_text("{ esto no es json")
    assert service_status.read_status() is None


def test_clear_status_borra(status_en_tmp):
    service_status.write_status(sio_connected=True, mqtt_connected=True)
    assert service_status.read_status() is not None

    service_status.clear_status()
    assert service_status.read_status() is None
    # Idempotente: borrar dos veces no lanza.
    service_status.clear_status()


def test_write_status_nunca_lanza(monkeypatch):
    """Es telemetría: no puede tumbar el servicio de impresión."""

    def explota():
        raise OSError("disco lleno")

    monkeypatch.setattr(service_status, "_status_file_path", explota)
    service_status.write_status(sio_connected=True, mqtt_connected=True)
