# coding=utf-8
"""
Tests de los márgenes del sistema (barra de estado / navegación).

Lo único crítico acá es que nunca lance: si falla, la UI debe quedar como antes
(sin margen extra), no romper el arranque de la app.
"""

from fiscalberry.ui import android_insets


def test_en_escritorio_devuelve_ceros():
    margenes = android_insets.get_system_insets()

    assert margenes == {"top": 0, "bottom": 0, "left": 0, "right": 0}


def test_siempre_devuelve_las_cuatro_claves():
    assert set(android_insets.get_system_insets()) == {"top", "bottom", "left", "right"}


def test_no_lanza_si_android_falla(monkeypatch):
    """Ante cualquier problema con las APIs de Android, ceros y a seguir."""

    class ActivityRota:
        @property
        def mActivity(self):
            raise RuntimeError("jnius roto")

    def autoclass_falso(_nombre):
        return ActivityRota()

    import sys
    import types

    jnius_falso = types.ModuleType("jnius")
    jnius_falso.autoclass = autoclass_falso
    monkeypatch.setitem(sys.modules, "jnius", jnius_falso)

    assert android_insets.get_system_insets() == {"top": 0, "bottom": 0, "left": 0, "right": 0}


def test_el_diccionario_devuelto_es_propio():
    """No debe compartir la constante: si el caller la muta, no contamina."""
    primero = android_insets.get_system_insets()
    primero["top"] = 999

    assert android_insets.get_system_insets()["top"] == 0
