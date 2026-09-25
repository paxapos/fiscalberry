# coding=utf-8
"""
Tests del contexto de Android compartido entre procesos.

En el proceso del servicio no hay Activity: usar PythonActivity.mActivity ahí
tira "'NoneType' object has no attribute 'getSystemService'". Lo que se fija es
que el helper nunca lance y que el caller reciba None cuando no hay contexto.
"""

from fiscalberry.common.android_context import get_android_context


def test_en_escritorio_devuelve_none():
    assert get_android_context() is None


def test_no_lanza_si_jnius_falla(monkeypatch):
    import sys
    import types

    def autoclass_roto(_nombre):
        raise RuntimeError("clase no encontrada")

    jnius_falso = types.ModuleType("jnius")
    jnius_falso.autoclass = autoclass_roto
    monkeypatch.setitem(sys.modules, "jnius", jnius_falso)

    assert get_android_context() is None


def test_usa_el_service_si_no_hay_activity(monkeypatch):
    """El caso del proceso del servicio: sin Activity, con Service."""
    import sys
    import types

    servicio = object()

    class SinActividad:
        mActivity = None

    class ConServicio:
        mService = servicio

    def autoclass_falso(nombre):
        return SinActividad if "Activity" in nombre else ConServicio

    jnius_falso = types.ModuleType("jnius")
    jnius_falso.autoclass = autoclass_falso
    monkeypatch.setitem(sys.modules, "jnius", jnius_falso)

    assert get_android_context() is servicio
