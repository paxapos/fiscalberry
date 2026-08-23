# coding=utf-8
"""
Limpieza de descargas viejas.

En Linux y Windows el staging se borra al terminar cada ciclo. En Android no se
puede: el APK tiene que seguir existiendo cuando la función retorna, porque lo
lee el instalador del sistema después. Si el usuario posterga la instalación,
ese APK (~44 MB) queda huérfano y el chequeo siguiente baja otro.

Sin esta limpieza, un usuario que dice "ahora no" cuatro veces por día llena el
teléfono en menos de una semana.
"""

import os
import time

import pytest

from fiscalberry.common.updater import staging


@pytest.fixture
def raiz(monkeypatch, tmp_path):
    d = tmp_path / "update-staging"
    d.mkdir()
    monkeypatch.setattr(staging, "staging_dir", lambda: str(d))
    return d


def _viejo(path, edad_horas):
    antiguo = time.time() - edad_horas * 3600
    os.utime(path, (antiguo, antiguo))


def test_borra_las_descargas_viejas(raiz):
    d = raiz / "fb-update-abc"
    d.mkdir()
    (d / "fiscalberry-android-gui.apk").write_bytes(b"x" * 1000)
    _viejo(str(d), 48)

    assert staging.cleanup_stale() == 1
    assert not d.exists()


def test_no_toca_una_descarga_en_curso(raiz):
    """Borrar el staging del ciclo actual abortaría una actualización viva."""
    d = raiz / "fb-update-actual"
    d.mkdir()
    (d / "asset.tar.gz").write_bytes(b"x")

    assert staging.cleanup_stale() == 0
    assert d.exists()


def test_respeta_el_umbral_de_edad(raiz):
    reciente = raiz / "fb-update-reciente"
    reciente.mkdir()
    _viejo(str(reciente), 2)

    antiguo = raiz / "fb-update-antiguo"
    antiguo.mkdir()
    _viejo(str(antiguo), 30)

    assert staging.cleanup_stale() == 1
    assert reciente.exists()
    assert not antiguo.exists()


def test_sin_directorio_de_staging_no_falla(monkeypatch, tmp_path):
    monkeypatch.setattr(staging, "staging_dir", lambda: str(tmp_path / "no-existe"))
    assert staging.cleanup_stale() == 0


def test_ignora_archivos_sueltos(raiz):
    suelto = raiz / "un-archivo.txt"
    suelto.write_text("x")
    _viejo(str(suelto), 99)

    assert staging.cleanup_stale() == 0
    assert suelto.exists()
