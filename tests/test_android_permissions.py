# coding=utf-8
"""
Tests de la lista de permisos que se piden en Android.

El caso que fijan estos tests es feo y silencioso: desde Android 11 (API 30), si
ACCESS_BACKGROUND_LOCATION viaja en el mismo pedido que otros permisos de
ubicación, el sistema IGNORA EL LOTE ENTERO — no aparece ningún diálogo y no se
otorga nada, ni siquiera los permisos no relacionados. En campo se veía como
"la app nunca me pide permisos".
"""

import pytest

from fiscalberry.android import permissions as perms

BACKGROUND_LOCATION = "android.permission.ACCESS_BACKGROUND_LOCATION"


def _permisos_para(monkeypatch, api_level):
    monkeypatch.setattr(perms, "ANDROID", True)
    monkeypatch.setattr(perms, "ANDROID_API_LEVEL", api_level)
    return perms.get_required_permissions()


@pytest.mark.parametrize("api_level", [23, 29, 30, 31, 33, 34, 35])
def test_nunca_se_pide_background_location(monkeypatch, api_level):
    assert BACKGROUND_LOCATION not in _permisos_para(monkeypatch, api_level)


def test_android_15_pide_notificaciones_y_bluetooth(monkeypatch):
    permisos = _permisos_para(monkeypatch, 35)

    assert "android.permission.POST_NOTIFICATIONS" in permisos
    assert "android.permission.BLUETOOTH_CONNECT" in permisos
    assert "android.permission.BLUETOOTH_SCAN" in permisos


def test_sin_ubicacion_desde_api_31(monkeypatch):
    """Desde Android 12 el escaneo BT no necesita ubicación: no asustar al usuario."""
    permisos = _permisos_para(monkeypatch, 35)

    assert "android.permission.ACCESS_FINE_LOCATION" not in permisos
    assert "android.permission.ACCESS_COARSE_LOCATION" not in permisos


def test_con_ubicacion_antes_de_api_31(monkeypatch):
    """En Android 10/11 el escaneo BT sí la necesita."""
    permisos = _permisos_para(monkeypatch, 30)

    assert "android.permission.ACCESS_COARSE_LOCATION" in permisos


def test_no_se_pide_schedule_exact_alarm(monkeypatch):
    """Solo se concede desde Ajustes: pedirlo no abre diálogo y ensucia la lista."""
    assert "android.permission.SCHEDULE_EXACT_ALARM" not in _permisos_para(monkeypatch, 35)


def test_notificaciones_solo_desde_api_33(monkeypatch):
    assert "android.permission.POST_NOTIFICATIONS" not in _permisos_para(monkeypatch, 31)
