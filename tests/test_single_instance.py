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


# ---------------------------------------------------------------------------
# Activación en Linux: socket Unix al lado del lockfile (#187)
# ---------------------------------------------------------------------------

@pytest.fixture
def socket_en_tmp(lock_en_tmp, monkeypatch):
    ruta = os.path.join(os.path.dirname(lock_en_tmp), si.ACTIVATION_SOCKET_NAME)
    monkeypatch.setattr(si, "_activation_socket_path", lambda: ruta)
    monkeypatch.setattr(si, "_listener", None)
    yield ruta
    si.stop_activation_listener()


def _esperar(condicion, segundos=3.0):
    import time
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return condicion()


def test_activacion_por_socket_muestra_la_ventana(socket_en_tmp):
    mostradas = []
    assert si.acquire_single_instance_lock() is True
    assert si.start_activation_listener(lambda: mostradas.append(1)) is True

    # Solo el usuario puede pedirle cosas a la instancia.
    assert oct(os.stat(socket_en_tmp).st_mode & 0o777) == "0o600"

    assert si.request_activation() is True
    assert _esperar(lambda: mostradas == [1])


def test_un_socket_viejo_no_impide_escuchar(socket_en_tmp):
    """Si la instancia anterior murió con kill -9, el archivo quedó ahí."""
    import socket as _socket
    viejo = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    viejo.bind(socket_en_tmp)
    viejo.close()

    mostradas = []
    si.acquire_single_instance_lock()
    assert si.start_activation_listener(lambda: mostradas.append(1)) is True
    assert si.request_activation() is True
    assert _esperar(lambda: mostradas == [1])


def test_un_pedido_desconocido_se_ignora(socket_en_tmp):
    import socket as _socket
    mostradas = []
    si.acquire_single_instance_lock()
    si.start_activation_listener(lambda: mostradas.append(1))

    cliente = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    cliente.connect(socket_en_tmp)
    cliente.sendall(b"rm -rf /\n")
    cliente.close()

    assert si.request_activation() is True
    assert _esperar(lambda: mostradas == [1])
    assert mostradas == [1]


def test_sin_instancia_viva_la_activacion_no_llega(socket_en_tmp):
    assert si.request_activation() is False


def test_segundo_proceso_activa_al_primero(socket_en_tmp, lock_en_tmp):
    """Proceso REAL aparte: lo que pasa al abrir el acceso directo dos veces."""
    mostradas = []
    si.acquire_single_instance_lock()
    si.start_activation_listener(lambda: mostradas.append(1))

    src_dir = os.path.abspath(os.path.join(os.path.dirname(si.__file__), "..", ".."))
    codigo = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {src_dir!r})
        from fiscalberry.common import single_instance as si
        si._lock_file_path = lambda: {lock_en_tmp!r}
        si._activation_socket_path = lambda: {socket_en_tmp!r}
        if si.acquire_single_instance_lock():
            sys.exit(3)
        sys.exit(0 if si.request_activation() else 5)
    """)
    proc = subprocess.run([sys.executable, "-c", codigo],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert _esperar(lambda: mostradas == [1])
