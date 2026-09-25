# coding=utf-8
"""
Instancia única y activación en Windows, con la API de Win32 simulada (#187).

En Windows no hay flock: el candado es un mutex con nombre
(`Local\\FiscalberrySingleInstance`), y "ya hay otra instancia" se lee como
ERROR_ALREADY_EXISTS al crearlo. El kernel de mentira de abajo reproduce las
dos propiedades que importan: un objeto con nombre existe mientras alguien
tenga un handle abierto, y un evento auto-reset despierta a una sola espera.
"""

import threading
import time

import pytest

from fiscalberry.common import single_instance as si


WAIT_TIMEOUT = 0x102


class KernelFalso:
    def __init__(self):
        self.refs = {}       # nombre -> handles abiertos
        self.handles = {}    # handle -> nombre
        self.senal = {}      # nombre del evento -> señalado
        self.primer_plano_permitido = False
        self._siguiente = 1
        self._lock = threading.Lock()

    def _abrir(self, nombre):
        with self._lock:
            handle = self._siguiente
            self._siguiente += 1
            self.handles[handle] = nombre
            self.refs[nombre] = self.refs.get(nombre, 0) + 1
            return handle

    def create_mutex(self, nombre):
        ya_existia = self.refs.get(nombre, 0) > 0
        return self._abrir(nombre), ya_existia

    def create_event(self, nombre):
        self.senal.setdefault(nombre, False)
        return self._abrir(nombre)

    def open_event(self, nombre):
        if self.refs.get(nombre, 0) == 0:
            return None
        return self._abrir(nombre)

    def set_event(self, handle):
        self.senal[self.handles[handle]] = True
        return True

    def wait(self, handle, timeout_ms):
        nombre = self.handles.get(handle)
        with self._lock:
            if self.senal.get(nombre):
                self.senal[nombre] = False  # auto-reset
                return si.WAIT_OBJECT_0
        time.sleep(0.01)
        return WAIT_TIMEOUT

    def close_handle(self, handle):
        with self._lock:
            nombre = self.handles.pop(handle, None)
            if nombre is None:
                return
            self.refs[nombre] -= 1
            if self.refs[nombre] == 0:
                del self.refs[nombre]
                self.senal.pop(nombre, None)

    def allow_set_foreground_window(self):
        self.primer_plano_permitido = True

    def existe(self, nombre):
        return self.refs.get(nombre, 0) > 0


@pytest.fixture
def kernel(monkeypatch):
    k = KernelFalso()
    monkeypatch.setattr(si, "_is_windows", lambda: True)
    monkeypatch.setattr(si, "_win32", k)
    monkeypatch.setattr(si, "_lock_file", None)
    monkeypatch.setattr(si, "_listener", None)
    monkeypatch.delenv("FISCALBERRY_LOCK_WAIT", raising=False)
    yield k
    si.release_single_instance_lock()


def otra_instancia_abierta(kernel):
    """Lo que deja en el kernel un Fiscalberry que ya está corriendo."""
    handle, _ = kernel.create_mutex(si.WINDOWS_MUTEX_NAME)
    return handle


# ---------------------------------------------------------------------------
# Candado
# ---------------------------------------------------------------------------

def test_toma_el_mutex_y_lo_libera(kernel):
    assert si.acquire_single_instance_lock() is True
    assert kernel.existe(si.WINDOWS_MUTEX_NAME)

    # Re-entrante: el entry point y ServiceController.start() lo piden los dos.
    assert si.acquire_single_instance_lock() is True
    assert kernel.refs[si.WINDOWS_MUTEX_NAME] == 1

    si.release_single_instance_lock()
    assert not kernel.existe(si.WINDOWS_MUTEX_NAME)


def test_con_otra_instancia_viva_no_arranca_ni_retiene_su_mutex(kernel):
    otra = otra_instancia_abierta(kernel)

    assert si.acquire_single_instance_lock() is False

    # El handle que se abrió para preguntar se cerró: si quedara abierto, el
    # mutex seguiría existiendo cuando la otra instancia muera, y el instalador
    # creería que Fiscalberry sigue abierto.
    assert kernel.refs[si.WINDOWS_MUTEX_NAME] == 1
    kernel.close_handle(otra)
    assert not kernel.existe(si.WINDOWS_MUTEX_NAME)


def test_espera_a_que_la_otra_instancia_termine(kernel, monkeypatch):
    """Relanzamiento post-actualización: el proceso viejo todavía está muriendo."""
    otra = otra_instancia_abierta(kernel)
    monkeypatch.setenv("FISCALBERRY_LOCK_WAIT", "30")

    esperas = []

    def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) == 3:
            kernel.close_handle(otra)  # la instancia vieja terminó de cerrar

    monkeypatch.setattr(si, "_sleep", dormir)

    assert si.acquire_single_instance_lock() is True
    assert len(esperas) == 3
    assert kernel.refs[si.WINDOWS_MUTEX_NAME] == 1


def test_la_espera_tiene_limite(kernel, monkeypatch):
    otra_instancia_abierta(kernel)
    monkeypatch.setenv("FISCALBERRY_LOCK_WAIT", "2")

    reloj = {"ahora": 0.0}
    monkeypatch.setattr(si, "_monotonic", lambda: reloj["ahora"])

    def dormir(segundos):
        reloj["ahora"] += segundos

    monkeypatch.setattr(si, "_sleep", dormir)

    assert si.acquire_single_instance_lock() is False
    assert reloj["ahora"] >= 2.0
    assert kernel.refs[si.WINDOWS_MUTEX_NAME] == 1


def test_sin_api_de_windows_arranca_igual(monkeypatch):
    """Mejor arrancar sin protección que no arrancar."""
    monkeypatch.setattr(si, "_is_windows", lambda: True)
    monkeypatch.setattr(si, "_win32", None)
    monkeypatch.setattr(si, "_lock_file", None)

    def sin_api():
        raise OSError("sin kernel32")

    monkeypatch.setattr(si, "_win32_api", sin_api)
    assert si.acquire_single_instance_lock() is True


# ---------------------------------------------------------------------------
# Activación
# ---------------------------------------------------------------------------

def esperar(condicion, segundos=3.0):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return condicion()


def test_la_segunda_instancia_pide_mostrar_la_ventana(kernel):
    mostradas = []
    assert si.acquire_single_instance_lock() is True
    assert si.start_activation_listener(lambda: mostradas.append(1)) is True

    # Lo que hace la segunda instancia antes de salir con código 0.
    assert si.request_activation() is True

    assert esperar(lambda: mostradas == [1])
    # Sin AllowSetForegroundWindow, Windows solo haría parpadear la barra de
    # tareas en vez de traer la ventana al frente.
    assert kernel.primer_plano_permitido
    # El handle del evento que abrió la segunda instancia se cerró.
    assert kernel.refs[si.WINDOWS_SHOW_EVENT_NAME] == 1


def test_cada_pedido_muestra_la_ventana_una_vez(kernel):
    mostradas = []
    si.acquire_single_instance_lock()
    si.start_activation_listener(lambda: mostradas.append(1))

    si.request_activation()
    assert esperar(lambda: len(mostradas) == 1)
    si.request_activation()
    assert esperar(lambda: len(mostradas) == 2)
    time.sleep(0.05)
    assert len(mostradas) == 2


def test_sin_instancia_que_escuche_la_activacion_no_llega(kernel):
    assert si.request_activation() is False


def test_al_liberar_se_deja_de_escuchar(kernel):
    si.acquire_single_instance_lock()
    si.start_activation_listener(lambda: None)
    assert kernel.existe(si.WINDOWS_SHOW_EVENT_NAME)

    si.release_single_instance_lock()

    assert not kernel.existe(si.WINDOWS_SHOW_EVENT_NAME)
    assert si.request_activation() is False
