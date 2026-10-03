# coding=utf-8
"""
Instancia única y activación en Windows, con la API de Windows simulada.

En Windows el candado es un mutex con nombre y el pedido de "mostrá la ventana"
es un evento con nombre. Estos tests corren en Linux: reemplazan las llamadas
a kernel32/user32 por un objeto que se comporta igual (un mutex existe mientras
alguien tenga un handle abierto; un evento auto-reset se apaga al despertar a
quien lo espera).
"""

import threading
import time

import pytest

from fiscalberry.common import single_instance as si


class ApiFalsa:
    """Mutex y eventos con nombre, como los ve un proceso de Windows."""

    def __init__(self):
        self.mutexes = {}       # nombre -> handles abiertos (de cualquier proceso)
        self.eventos = {}       # nombre -> threading.Event
        self.cerrados = []
        self.primer_plano = 0
        self._lock = threading.Lock()

    # -- mutex
    def crear_mutex(self, nombre):
        with self._lock:
            ya_existia = self.mutexes.get(nombre, 0) > 0
            self.mutexes[nombre] = self.mutexes.get(nombre, 0) + 1
        return ("mutex", nombre, object()), ya_existia

    def otro_proceso_toma(self, nombre=si.WINDOWS_MUTEX_NAME):
        with self._lock:
            self.mutexes[nombre] = self.mutexes.get(nombre, 0) + 1

    def otro_proceso_suelta(self, nombre=si.WINDOWS_MUTEX_NAME):
        with self._lock:
            self.mutexes[nombre] -= 1

    # -- eventos
    def crear_evento(self, nombre):
        with self._lock:
            self.eventos.setdefault(nombre, threading.Event())
        return ("evento", nombre)

    def abrir_evento(self, nombre):
        with self._lock:
            return ("evento", nombre) if nombre in self.eventos else None

    def senalizar(self, handle):
        self.eventos[handle[1]].set()
        return True

    def esperar(self, handle, milisegundos):
        ev = self.eventos[handle[1]]
        if ev.wait(milisegundos / 1000.0):
            ev.clear()  # auto-reset
            return True
        return False

    # -- comunes
    def cerrar(self, handle):
        self.cerrados.append(handle)
        if handle and handle[0] == "mutex":
            with self._lock:
                self.mutexes[handle[1]] -= 1

    def permitir_primer_plano(self):
        self.primer_plano += 1


@pytest.fixture
def windows(monkeypatch):
    api = ApiFalsa()
    monkeypatch.setattr(si, "_es_windows", lambda: True)
    monkeypatch.setattr(si, "_api", api)
    monkeypatch.setattr(si, "_mutex_handle", None)
    monkeypatch.setattr(si, "_lock_file", None)
    monkeypatch.delenv("FISCALBERRY_LOCK_WAIT", raising=False)
    yield api
    si.release_single_instance_lock()


def test_toma_el_mutex_y_es_reentrante(windows):
    assert si.acquire_single_instance_lock() is True
    assert si.holds_single_instance_lock()
    assert windows.mutexes[si.WINDOWS_MUTEX_NAME] == 1

    # cli/main y ServiceController.start() lo vuelven a pedir: no abre otro.
    assert si.acquire_single_instance_lock() is True
    assert windows.mutexes[si.WINDOWS_MUTEX_NAME] == 1

    si.release_single_instance_lock()
    assert windows.mutexes[si.WINDOWS_MUTEX_NAME] == 0
    assert not si.holds_single_instance_lock()


def test_con_otra_instancia_viva_no_arranca_y_suelta_el_handle(windows):
    windows.otro_proceso_toma()

    assert si.acquire_single_instance_lock() is False
    assert not si.holds_single_instance_lock()
    # El handle que se abrió para preguntar se cerró: si quedara abierto, el
    # mutex seguiría existiendo después de que muera la otra instancia y nadie
    # podría volver a arrancar.
    assert windows.mutexes[si.WINDOWS_MUTEX_NAME] == 1


def test_espera_a_que_la_instancia_vieja_termine(windows, monkeypatch):
    """El relanzado post-actualización arranca con el proceso viejo muriendo."""
    windows.otro_proceso_toma()
    monkeypatch.setenv("FISCALBERRY_LOCK_WAIT", "5")
    threading.Timer(0.6, windows.otro_proceso_suelta).start()

    t0 = time.monotonic()
    assert si.acquire_single_instance_lock() is True
    assert 0.5 <= time.monotonic() - t0 < 4


def test_la_espera_tiene_un_limite(windows, monkeypatch):
    windows.otro_proceso_toma()
    monkeypatch.setenv("FISCALBERRY_LOCK_WAIT", "0.6")

    t0 = time.monotonic()
    assert si.acquire_single_instance_lock() is False
    assert time.monotonic() - t0 < 3


def test_sin_api_de_windows_arranca_igual(windows, monkeypatch):
    """Mejor arrancar sin protección que no arrancar."""
    def explota():
        raise OSError("sin kernel32")

    monkeypatch.setattr(si, "_api", None)
    monkeypatch.setattr(si, "_api_windows", explota)
    assert si.acquire_single_instance_lock() is True


def test_la_segunda_instancia_le_pide_a_la_viva_que_se_muestre(windows):
    assert si.acquire_single_instance_lock() is True
    pedidos = []
    escucha = si.start_activation_listener(lambda: pedidos.append(1))
    assert escucha is not None
    try:
        # Lo que hace el segundo proceso (comparten la "API" porque comparten
        # el espacio de nombres de la sesión).
        assert si._notificar_windows(timeout=2) is True
        assert _esperar(lambda: pedidos == [1])
        # La instancia nueva habilita a la vieja a traer su ventana al frente.
        assert windows.primer_plano == 1
    finally:
        escucha.stop()


def test_sin_nadie_escuchando_el_aviso_falla_sin_colgarse(windows):
    t0 = time.monotonic()
    assert si._notificar_windows(timeout=0.4) is False
    assert time.monotonic() - t0 < 2


def test_solo_escucha_quien_tiene_el_candado(windows):
    windows.otro_proceso_toma()
    assert si.acquire_single_instance_lock() is False
    assert si.start_activation_listener(lambda: None) is None


def test_un_callback_que_falla_no_mata_al_que_escucha(windows):
    assert si.acquire_single_instance_lock() is True
    llamadas = []

    def callback():
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("la UI todavía no estaba lista")

    escucha = si.start_activation_listener(callback)
    try:
        assert si._notificar_windows(timeout=2)
        assert _esperar(lambda: len(llamadas) == 1)
        assert si._notificar_windows(timeout=2)
        assert _esperar(lambda: len(llamadas) == 2)
    finally:
        escucha.stop()


def _esperar(condicion, timeout=3.0):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.02)
    return condicion()
