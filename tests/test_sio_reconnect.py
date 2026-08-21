# coding=utf-8
"""
Tests de reconexión de FiscalberrySio y del ServiceController (fix Android).

Cubren la causa raíz del "no reconecta tras apagar la pantalla" (Doze):
  - _run() crea un socketio.Client NUEVO en cada ciclo de conexión, en vez de
    reusar uno con estado stale ("Already connected" sobre un socket muerto).
  - Un Client viejo con connected=True no bloquea el ciclo siguiente.
  - force_reconnect() cierra el cliente actual para reciclar la conexión.
  - ServiceController.reset_singleton() realmente permite el re-init
    (regresión del guard hasattr/getattr en __init__).

Se mockea socketio.Client por completo: sin red.
"""

import threading

import pytest

pytest.importorskip("socketio")

from fiscalberry.common import fiscalberry_sio as sio_module
from fiscalberry.common.fiscalberry_sio import FiscalberrySio


class FakeSioClient:
    """Doble de socketio.Client que registra llamadas."""

    instances = []

    def __init__(self, *a, **k):
        self.connected = False
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.handlers = {}
        self.sid = "fake-sid"
        self._wait_event = threading.Event()
        FakeSioClient.instances.append(self)

    def event(self, namespace=None):
        def decorator(fn):
            self.handlers[fn.__name__] = fn
            return fn

        return decorator

    def connect(self, *a, **k):
        if self.connected:
            raise Exception("Already connected")
        self.connected = True
        self.connect_calls += 1

    def wait(self):
        # Retorna cuando alguien llama disconnect() (como socketio real).
        self._wait_event.wait(timeout=5)

    def disconnect(self):
        self.disconnect_calls += 1
        self.connected = False
        self._wait_event.set()


@pytest.fixture
def fresh_sio(monkeypatch, tmp_path):
    """FiscalberrySio limpio con socketio.Client mockeado y config en tmp."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    FakeSioClient.instances = []
    monkeypatch.setattr(sio_module.socketio, "Client", FakeSioClient)
    FiscalberrySio.reset_singleton()
    FiscalberrySio._instance = None
    sio = FiscalberrySio("http://fake-server", "fake-uuid")
    yield sio
    try:
        sio.stop()
    except Exception:
        pass
    FiscalberrySio._instance = None


def test_run_crea_cliente_nuevo_por_ciclo(fresh_sio):
    """Cada ciclo de _run debe descartar el Client anterior y crear uno nuevo."""
    first_client = fresh_sio.sio
    assert isinstance(first_client, FakeSioClient)

    fresh_sio.stop_event.clear()
    t = threading.Thread(target=fresh_sio._run, daemon=True)
    t.start()
    # Esperar a que el nuevo cliente conecte
    for _ in range(50):
        if fresh_sio.sio is not first_client and fresh_sio.sio.connected:
            break
        threading.Event().wait(0.05)

    assert fresh_sio.sio is not first_client, "_run debe crear un Client nuevo"
    assert fresh_sio.sio.connect_calls == 1
    # El viejo tiene que haber sido cerrado
    assert first_client.disconnect_calls >= 1

    fresh_sio.sio.disconnect()
    t.join(timeout=5)
    assert not t.is_alive()


def test_cliente_stale_no_bloquea_el_siguiente_ciclo(fresh_sio):
    """
    Regresión del bug principal: un Client viejo con connected=True (socket
    half-open tras Doze) hacía que connect() lanzara "Already connected" en
    loop eterno. Con el fix, el ciclo siguiente conecta igual.
    """
    # Simular el estado zombie: el cliente actual se cree conectado
    fresh_sio.sio.connected = True

    fresh_sio.stop_event.clear()
    t = threading.Thread(target=fresh_sio._run, daemon=True)
    t.start()
    for _ in range(50):
        if fresh_sio.sio.connect_calls and fresh_sio.sio.connected:
            break
        threading.Event().wait(0.05)

    assert fresh_sio.sio.connected, "el ciclo nuevo debe conectar pese al cliente stale"
    assert fresh_sio.sio.connect_calls == 1

    fresh_sio.sio.disconnect()
    t.join(timeout=5)


def test_force_reconnect_desbloquea_wait(fresh_sio):
    """force_reconnect() debe cerrar el cliente y hacer retornar el hilo de _run."""
    fresh_sio.stop_event.clear()
    t = threading.Thread(target=fresh_sio._run, daemon=True)
    t.start()
    for _ in range(50):
        if fresh_sio.sio.connected:
            break
        threading.Event().wait(0.05)
    assert fresh_sio.sio.connected

    fresh_sio.force_reconnect()
    t.join(timeout=5)
    assert not t.is_alive(), "tras force_reconnect el hilo de _run debe terminar"


def test_run_no_conecta_si_stop_pedido(fresh_sio):
    """Si stop() llegó antes/durante la recreación del cliente, no reconectar."""
    fresh_sio.stop_event.set()
    fresh_sio._run()
    assert fresh_sio.sio.connect_calls == 0


def test_service_controller_reset_singleton_permite_reinit(monkeypatch, tmp_path):
    """
    Regresión: __init__ chequeaba hasattr(self, 'initialized') pero
    reset_singleton() seteaba initialized=False (el atributo seguía
    existiendo), así que el re-init jamás corría.
    """
    from fiscalberry.common.service_controller import ServiceController

    ServiceController._instance = None
    controller = ServiceController.__new__(ServiceController)
    controller.initialized = True

    ServiceController._instance = controller
    ServiceController.reset_singleton()

    assert controller.initialized is False
    # Con el guard viejo (hasattr) esto retornaba temprano sin inicializar nada.
    # Con getattr, __init__ debe intentar el init completo de nuevo: lo
    # verificamos observando que ya no corta en el guard (configberry se setea
    # o lanza RuntimeError por config incompleta, ambas prueban que avanzó).
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    try:
        controller.__init__()
        avanzo = hasattr(controller, "configberry")
    except RuntimeError:
        avanzo = True
    assert avanzo, "tras reset_singleton, __init__ debe reintentar el init completo"
    ServiceController._instance = None
