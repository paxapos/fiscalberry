# coding=utf-8
"""
Tests del candado de instancia única (single_instance).

El candado usa flock(): el segundo proceso que intenta tomarlo debe fallar
mientras el primero viva, y el kernel lo libera al morir el dueño.
"""

import os
import subprocess
import sys
import textwrap

import pytest

from fiscalberry.common import single_instance as si

pytestmark = pytest.mark.skipif(si.fcntl is None, reason="plataforma sin fcntl")


@pytest.fixture
def lock_en_tmp(tmp_path, monkeypatch):
    lock_path = tmp_path / si.LOCK_FILE_NAME
    monkeypatch.setattr(si, "_lock_file_path", lambda: str(lock_path))
    monkeypatch.setattr(si, "_lock_file", None)
    yield str(lock_path)
    si.release_single_instance_lock()


def test_toma_y_libera_el_candado(lock_en_tmp):
    assert si.acquire_single_instance_lock() is True
    assert os.path.exists(lock_en_tmp)
    # Reentrante dentro del mismo proceso (cli/main y ServiceController.start).
    assert si.acquire_single_instance_lock() is True
    si.release_single_instance_lock()
    # Después de liberar se puede volver a tomar.
    assert si.acquire_single_instance_lock() is True


def test_segundo_proceso_no_puede_arrancar(lock_en_tmp):
    assert si.acquire_single_instance_lock() is True

    # Proceso REAL aparte (flock no bloquea dentro del mismo proceso).
    src_dir = os.path.abspath(os.path.join(os.path.dirname(si.__file__), "..", ".."))
    codigo = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {src_dir!r})
        from fiscalberry.common import single_instance as si
        si._lock_file_path = lambda: {lock_en_tmp!r}
        sys.exit(0 if si.acquire_single_instance_lock() else 7)
    """)
    proc = subprocess.run([sys.executable, "-c", codigo],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 7, (
        "el segundo proceso debería haber sido rechazado; "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )

    # Al liberar el primero, un proceso nuevo sí puede tomarlo.
    si.release_single_instance_lock()
    proc = subprocess.run([sys.executable, "-c", codigo],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, (
        f"con el candado libre debería arrancar; stderr={proc.stderr!r}"
    )
