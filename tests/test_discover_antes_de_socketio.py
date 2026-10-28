"""
SocketIO no conecta mientras el discover está en vuelo.

Los dos crean la Paxaprinter en el servidor si no existe (PHP en el discover,
Nest en el connect) y `machine_uuid` no es único: lanzados a la vez generaban
filas duplicadas. La vinculación adoptaba una, el gateway seguía mirando la
otra, la app nunca recibía start_rabbit y al reintentar el link el servidor
respondía 404 "Paxaprinter ya adoptada".
"""

import threading
import time

from fiscalberry.common.service_controller import ServiceController


def _controller_con_discover(hilo):
    ctrl = ServiceController.__new__(ServiceController)
    ctrl.discover_thread = hilo
    return ctrl


def test_espera_a_que_termine_el_discover():
    terminado = threading.Event()

    def discover_lento():
        time.sleep(0.3)
        terminado.set()

    hilo = threading.Thread(target=discover_lento, daemon=True)
    hilo.start()

    _controller_con_discover(hilo)._esperar_discover()

    assert terminado.is_set()


def test_no_bloquea_para_siempre_si_el_discover_cuelga(monkeypatch):
    liberar = threading.Event()
    hilo = threading.Thread(target=liberar.wait, daemon=True)
    hilo.start()

    monkeypatch.setattr(ServiceController, "DISCOVER_WAIT_TIMEOUT", 0.1)
    inicio = time.monotonic()
    _controller_con_discover(hilo)._esperar_discover()

    assert time.monotonic() - inicio < 2
    liberar.set()


def test_sin_hilo_de_discover_no_falla():
    _controller_con_discover(None)._esperar_discover()
