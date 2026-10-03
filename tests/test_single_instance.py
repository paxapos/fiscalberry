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


# --------------------------------------------------------------------------
# Activación: abrir Fiscalberry de nuevo muestra la ventana de la instancia viva
# --------------------------------------------------------------------------

@pytest.fixture
def socket_en_tmp(lock_en_tmp, monkeypatch, tmp_path):
    ruta = tmp_path / si.SOCKET_FILE_NAME
    monkeypatch.setattr(si, "_socket_path", lambda: str(ruta))
    return str(ruta)


def _esperar(condicion, timeout=3.0):
    import time
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.02)
    return condicion()


def test_la_instancia_nueva_le_pide_a_la_viva_que_se_muestre(socket_en_tmp):
    assert si.acquire_single_instance_lock() is True
    pedidos = []
    escucha = si.start_activation_listener(lambda: pedidos.append(1))
    assert escucha is not None
    try:
        assert si.notify_running_instance(timeout=2) is True
        assert _esperar(lambda: pedidos == [1])
    finally:
        escucha.stop()
    # Al dejar de escuchar se borra el socket.
    assert not os.path.exists(socket_en_tmp)


def test_un_socket_viejo_de_un_crash_no_impide_escuchar(socket_en_tmp):
    with open(socket_en_tmp, "w") as fh:
        fh.write("resto de una ejecución que murió")

    assert si.acquire_single_instance_lock() is True
    pedidos = []
    escucha = si.start_activation_listener(lambda: pedidos.append(1))
    try:
        assert si.notify_running_instance(timeout=2) is True
        assert _esperar(lambda: pedidos == [1])
    finally:
        escucha.stop()


def test_sin_el_candado_no_escucha_ni_toca_el_socket_ajeno(socket_en_tmp):
    """Reemplazar el socket le robaría el canal a la instancia que sí corre."""
    with open(socket_en_tmp, "w") as fh:
        fh.write("socket de la instancia viva")

    assert si.start_activation_listener(lambda: None) is None
    assert os.path.exists(socket_en_tmp)


def test_sin_nadie_escuchando_el_aviso_falla_rapido(socket_en_tmp):
    import time
    t0 = time.monotonic()
    assert si.notify_running_instance(timeout=0.4) is False
    assert time.monotonic() - t0 < 2


def test_mensajes_ajenos_al_socket_se_ignoran(socket_en_tmp):
    import socket

    assert si.acquire_single_instance_lock() is True
    pedidos = []
    escucha = si.start_activation_listener(lambda: pedidos.append(1))
    try:
        cliente = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        cliente.connect(socket_en_tmp)
        cliente.sendall(b"otra")
        cliente.close()
        assert si.notify_running_instance(timeout=2) is True
        assert _esperar(lambda: pedidos == [1])
    finally:
        escucha.stop()
