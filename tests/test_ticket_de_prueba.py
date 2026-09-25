# coding=utf-8
"""
Ticket de prueba del asistente (#172).

Lo que se fija acá:

- La prueba usa el mismo camino de driver que producción, pero no toca el
  config.ini ni publica errores en el topic del backend.
- El éxito técnico y el papel confirmado son cosas distintas: sin las dos, no
  se guarda nada.
- En los transportes bidireccionales se lee el estado real (DLE EOT) antes y
  después de imprimir, y cada problema trae una acción concreta.
- En una cola de Windows, que el spooler acepte el trabajo no alcanza, y una
  prueba que no se confirma no queda pendiente (no hay "ticket fantasma").
"""

import configparser
import os
import socket
import threading

import pytest

pytest.importorskip("escpos")

from escpos.exceptions import DeviceNotFoundError  # noqa: E402
from escpos.printer import Dummy  # noqa: E402

from fiscalberry.common import printer_test as pt  # noqa: E402
from fiscalberry.common.ComandosHandler import BuiltDriver, DriverError, build_driver  # noqa: E402
from fiscalberry.common.printer_setup import PrinterCandidate, PrinterSetupService  # noqa: E402
from fiscalberry.common.rabbitmq import error_publisher  # noqa: E402


# Bytes de estado DLE EOT (bits fijos 1 y 4 en 1: 0x12).
EN_LINEA = 0x12
FUERA_DE_LINEA = 0x12 | 0x08
SIN_CAUSA = 0x12
TAPA_ABIERTA = 0x12 | 0x04
SIN_PAPEL_PARADA = 0x12 | 0x20
PAPEL_OK = 0x12
PAPEL_POR_ACABARSE = 0x12 | 0x0C
PAPEL_AGOTADO = 0x12 | 0x60

ESTADO_OK = {1: EN_LINEA, 2: SIN_CAUSA, 4: PAPEL_OK}


class SocketFalso:
    def __init__(self):
        self.timeout = 10.0
        self.timeouts_vistos = []

    def gettimeout(self):
        return self.timeout

    def settimeout(self, valor):
        self.timeouts_vistos.append(valor)
        self.timeout = valor


class ImpresoraFalsa(Dummy):
    """
    Dummy de python-escpos (acumula lo impreso) que además contesta DLE EOT.
    `estados` None = no contesta (como muchas impresoras de red).
    """

    def __init__(self, estados=None, estados_despues=None, fallar_al_abrir=None):
        super().__init__()
        self.estados = estados
        self.estados_despues = estados_despues
        self.fallar_al_abrir = fallar_al_abrir
        self.socket = SocketFalso()
        self.consultas = []
        self.cerrada = False
        self._n = None

    @property
    def device(self):
        if self.fallar_al_abrir is not None:
            raise self.fallar_al_abrir
        return self.socket

    def _raw(self, msg):
        if msg[:2] == pt.DLE_EOT and len(msg) == 3:
            self._n = msg[2]
            self.consultas.append(self._n)
            return
        super()._raw(msg)

    def _read(self):
        estados = self.estados
        if self.estados_despues is not None and self.output:
            estados = self.estados_despues
        if estados is None or self._n not in estados:
            raise socket.timeout("timed out")
        return bytes([estados[self._n]])

    def close(self):
        self.cerrada = True


def constructor(impresora, configs=None):
    def construir(config):
        if configs is not None:
            configs.append(config)
        return BuiltDriver(impresora, "Network", None, dict(config))
    return construir


def info(candidate, **kw):
    datos = dict(commerce="Pizzería Don Pepe", alias="Cocina", code="K7QA")
    datos.update(kw)
    return pt.PrintTestInfo.for_candidate(candidate, **datos)


RED = PrinterCandidate.network("192.168.1.80")


# ---------------------------------------------------------------------------
# El ticket
# ---------------------------------------------------------------------------

def test_el_ticket_identifica_comercio_impresora_conexion_codigo_y_hora():
    from datetime import datetime

    impresora = ImpresoraFalsa()
    datos = pt.PrintTestInfo.for_candidate(
        RED, commerce="Pizzeria Don Pepe", alias="Cocina", code="K7QA",
        now=datetime(2026, 9, 25, 14, 30, 5))

    pt.render_test_ticket(impresora, datos)

    salida = impresora.output
    for texto in (b"PRUEBA", b"K7QA", b"Pizzeria Don Pepe", b"Cocina",
                  b"Red (192.168.1.80)", b"25/09/2026 14:30:05"):
        assert texto in salida, texto
    # Termina cortando el papel (GS V).
    assert b"\x1dV" in salida[-8:]


def test_el_codigo_es_corto_y_sin_caracteres_que_se_confunden():
    codigos = {pt.new_test_code() for _ in range(200)}
    assert all(len(c) == pt.CODE_LENGTH for c in codigos)
    assert not set("".join(codigos)) & set("0O1IL2Z5S8B")
    assert len(codigos) > 150  # no se repite a cada rato


# ---------------------------------------------------------------------------
# Estado real por DLE EOT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("estados,problema", [
    ({1: EN_LINEA, 2: SIN_CAUSA, 4: PAPEL_OK}, None),
    ({1: FUERA_DE_LINEA, 2: SIN_CAUSA, 4: PAPEL_OK}, pt.PROBLEM_OFFLINE),
    ({1: FUERA_DE_LINEA, 2: TAPA_ABIERTA, 4: PAPEL_OK}, pt.PROBLEM_COVER_OPEN),
    ({1: FUERA_DE_LINEA, 2: SIN_PAPEL_PARADA, 4: PAPEL_AGOTADO}, pt.PROBLEM_PAPER_OUT),
    ({1: FUERA_DE_LINEA, 2: 0x12 | 0x40, 4: PAPEL_OK}, pt.PROBLEM_OFFLINE),
    ({1: EN_LINEA, 2: 0x12 | 0x40, 4: PAPEL_OK}, pt.PROBLEM_PRINTER_ERROR),
])
def test_el_estado_se_traduce_en_un_problema(estados, problema):
    estado = pt.read_status(ImpresoraFalsa(estados))
    assert estado.known
    assert estado.blocking_problem == problema


def test_poco_papel_es_un_aviso_y_no_impide_imprimir():
    estado = pt.read_status(ImpresoraFalsa({1: EN_LINEA, 2: SIN_CAUSA, 4: PAPEL_POR_ACABARSE}))
    assert estado.blocking_problem is None
    assert estado.warning == pt.PROBLEM_PAPER_NEAR_END


def test_si_no_contesta_el_estado_es_desconocido_y_no_es_error():
    impresora = ImpresoraFalsa(estados=None)
    estado = pt.read_status(impresora)
    assert estado == pt.UNKNOWN_STATUS
    assert not estado.known
    # Tras la primera consulta sin respuesta no se insiste con las otras.
    assert impresora.consultas == [1]


def test_la_espera_del_estado_es_corta_y_despues_se_restaura():
    impresora = ImpresoraFalsa(ESTADO_OK)
    pt.read_status(impresora, timeout=1.5)
    assert impresora.socket.timeouts_vistos == [1.5, 10.0]


def test_respuestas_que_no_son_de_estado_se_ignoran():
    assert pt.status_byte(b"") is None
    assert pt.status_byte(b"\xff\x00") is None
    assert pt.status_byte(b"\x00\x12") == 0x12


# ---------------------------------------------------------------------------
# La prueba en un transporte bidireccional (red, USB directo, COM)
# ---------------------------------------------------------------------------

def test_prueba_exitosa_espera_la_confirmacion_en_papel():
    impresora = ImpresoraFalsa(ESTADO_OK)

    resultado = pt.run_print_test(RED, info(RED), builder=constructor(impresora))

    assert resultado.technical_success is True
    assert resultado.problem is None
    assert b"K7QA" in impresora.output
    # Estado leído antes Y después de imprimir.
    assert resultado.status_before.known and resultado.status_after.known
    assert impresora.cerrada
    # El éxito técnico solo no alcanza para guardar.
    assert resultado.paper_confirmed is False
    assert resultado.can_save is False
    assert resultado.confirm_paper(True) is True
    assert resultado.can_save is True


def test_con_la_tapa_abierta_no_se_imprime_y_se_dice_que_hacer():
    impresora = ImpresoraFalsa({1: FUERA_DE_LINEA, 2: TAPA_ABIERTA, 4: PAPEL_OK})

    resultado = pt.run_print_test(RED, info(RED), builder=constructor(impresora))

    assert resultado.technical_success is False
    assert resultado.problem == pt.PROBLEM_COVER_OPEN
    assert "tapa" in resultado.action.lower()
    assert impresora.output == b""


def test_si_se_queda_sin_papel_al_imprimir_la_prueba_falla():
    impresora = ImpresoraFalsa(ESTADO_OK,
                               estados_despues={1: FUERA_DE_LINEA, 2: SIN_PAPEL_PARADA,
                                                4: PAPEL_AGOTADO})

    resultado = pt.run_print_test(RED, info(RED), builder=constructor(impresora))

    assert resultado.technical_success is False
    assert resultado.problem == pt.PROBLEM_PAPER_OUT
    assert "rollo" in resultado.action


def test_impresora_que_no_contesta_estado_igual_puede_imprimir():
    impresora = ImpresoraFalsa(estados=None)

    resultado = pt.run_print_test(RED, info(RED), builder=constructor(impresora))

    assert resultado.technical_success is True
    assert not resultado.status_before.known


@pytest.mark.parametrize("causa,problema", [
    (ConnectionRefusedError(111, "Connection refused"), pt.PROBLEM_REFUSED),
    (socket.timeout("timed out"), pt.PROBLEM_TIMEOUT),
    (OSError(113, "No route to host"), pt.PROBLEM_NOT_FOUND),
])
def test_errores_de_conexion_con_accion_concreta(causa, problema):
    try:
        try:
            raise causa
        except OSError:
            # Así lo envuelve python-escpos al abrir el socket.
            raise DeviceNotFoundError("Could not open socket for 192.168.1.80")
    except DeviceNotFoundError as envuelto:
        error = envuelto

    impresora = ImpresoraFalsa(ESTADO_OK, fallar_al_abrir=error)
    resultado = pt.run_print_test(RED, info(RED), builder=constructor(impresora))

    assert resultado.technical_success is False
    assert resultado.problem == problema
    assert resultado.action


def test_un_driver_que_no_existe_se_explica():
    candidato = PrinterCandidate.usbprint("ruta", 0x04B8, 0x0202, "S1")

    resultado = pt.run_print_test(candidato, info(candidato))

    assert resultado.technical_success is False
    assert resultado.problem == pt.PROBLEM_DRIVER


# ---------------------------------------------------------------------------
# Cola de Windows: seguimiento del trabajo y nada de tickets fantasma
# ---------------------------------------------------------------------------

class Win32PrintFalso:
    """Cola de Windows de mentira: `plan` son los estados que va mostrando el trabajo."""

    def __init__(self, plan):
        self.plan = list(plan)   # None = ya no está en la cola
        self.borrados = []
        self.abiertas = 0

    def OpenPrinter(self, nombre):
        self.abiertas += 1
        return "handle"

    def ClosePrinter(self, handle):
        self.abiertas -= 1

    def EnumJobs(self, handle, primero, cantidad, nivel):
        if self.borrados:
            return []
        estado = self.plan[0] if len(self.plan) == 1 else self.plan.pop(0)
        return [] if estado is None else [{"JobId": 42, "Status": estado, "pDocument": "x"}]

    def SetJob(self, handle, job_id, nivel, info_, comando):
        assert comando == pt.JOB_CONTROL_DELETE
        self.borrados.append(job_id)


class ColaFalsa(Dummy):
    """Win32Raw de mentira: StartDocPrinter asigna el id de trabajo al abrir."""

    def __init__(self, fallar_al_abrir=None):
        super().__init__()
        self.current_job = None
        self.fallar_al_abrir = fallar_al_abrir
        self.cerrada = False

    def _raw(self, msg):
        if self.fallar_al_abrir is not None:
            raise self.fallar_al_abrir
        self.current_job = 42
        super()._raw(msg)

    def close(self):
        self.cerrada = True


COLA = PrinterCandidate.windows_queue("EPSON TM-T20", "USB001")


@pytest.fixture
def cola(monkeypatch):
    monkeypatch.setattr(pt.Win32JobTracker, "POLL_SECONDS", 0.001)

    def armar(plan):
        win32 = Win32PrintFalso(plan)

        def fabrica(nombre, job_id):
            assert nombre == "EPSON TM-T20"
            return pt.Win32JobTracker(nombre, job_id, win32print=win32)

        return win32, fabrica
    return armar


def test_el_trabajo_tiene_que_salir_de_la_cola(cola):
    win32, fabrica = cola([pt.JOB_STATUS_SPOOLING, pt.JOB_STATUS_PRINTING, None])
    impresora = ColaFalsa()

    resultado = pt.run_print_test(COLA, info(COLA), builder=constructor(impresora),
                                  tracker_factory=fabrica, job_timeout=5)

    assert resultado.technical_success is True
    assert impresora.cerrada
    assert win32.borrados == []
    assert win32.abiertas == 0


def test_si_la_impresora_no_toma_el_trabajo_se_borra_de_la_cola(cola):
    """El spooler lo aceptó, pero eso no es éxito: y no puede salir más tarde."""
    win32, fabrica = cola([0])  # queda "en cola" para siempre

    resultado = pt.run_print_test(COLA, info(COLA), builder=constructor(ColaFalsa()),
                                  tracker_factory=fabrica, job_timeout=0.05)

    assert resultado.technical_success is False
    assert resultado.problem == pt.PROBLEM_JOB_STUCK
    assert win32.borrados == [42]
    assert resultado.job_cancelled is True


@pytest.mark.parametrize("estado,problema", [
    (pt.JOB_STATUS_OFFLINE, pt.PROBLEM_OFFLINE),
    (pt.JOB_STATUS_PAPEROUT, pt.PROBLEM_PAPER_OUT),
    (pt.JOB_STATUS_ERROR, pt.PROBLEM_PRINTER_ERROR),
    (pt.JOB_STATUS_PAUSED, pt.PROBLEM_OFFLINE),
])
def test_un_trabajo_con_error_se_explica_y_se_borra(cola, estado, problema):
    win32, fabrica = cola([estado])

    resultado = pt.run_print_test(COLA, info(COLA), builder=constructor(ColaFalsa()),
                                  tracker_factory=fabrica, job_timeout=5)

    assert resultado.problem == problema
    assert win32.borrados == [42]


def test_si_no_se_confirma_en_papel_no_queda_nada_pendiente(cola):
    win32, fabrica = cola([None])
    resultado = pt.run_print_test(COLA, info(COLA), builder=constructor(ColaFalsa()),
                                  tracker_factory=fabrica, job_timeout=5)
    assert resultado.technical_success

    assert resultado.confirm_paper(False) is False
    assert resultado.can_save is False
    # Ya había salido de la cola: nada que borrar, y no se intenta a ciegas.
    assert win32.borrados == []


def test_cancelar_la_prueba_borra_lo_pendiente(cola):
    win32, fabrica = cola([0])
    tracker = fabrica("EPSON TM-T20", 42)
    resultado = pt.PrintTestResult(technical_success=True, tracker=tracker)

    assert resultado.cancel() is True
    assert win32.borrados == [42]
    # Cancelar dos veces no vuelve a tocar la cola.
    resultado.cancel()
    assert win32.borrados == [42]


def test_acceso_denegado_a_la_cola(cola):
    class ErrorWin32(Exception):
        def __init__(self):
            super().__init__(5, "StartDocPrinter", "Acceso denegado.")
            self.winerror = 5

    win32, fabrica = cola([None])
    resultado = pt.run_print_test(COLA, info(COLA),
                                  builder=constructor(ColaFalsa(fallar_al_abrir=ErrorWin32())),
                                  tracker_factory=fabrica)

    assert resultado.problem == pt.PROBLEM_ACCESS_DENIED
    assert "otros programas" in resultado.action


# ---------------------------------------------------------------------------
# Sin efectos secundarios: ni config.ini, ni errores al backend, ni mutaciones
# ---------------------------------------------------------------------------

def test_la_prueba_no_publica_en_el_topic_de_errores(monkeypatch):
    publicados = []
    monkeypatch.setattr(error_publisher._error_dispatcher, "submit",
                        lambda item: publicados.append(item["error_type"]))

    def constructor_que_publica(config):
        # Como haría cualquier código del camino de impresión ante un error.
        error_publisher.publish_error("PRINTER_OFFLINE", "sin papel")
        raise DriverError("falla simulada")

    resultado = pt.run_print_test(RED, info(RED), builder=constructor_que_publica)

    assert resultado.technical_success is False
    assert publicados == []
    # Fuera de la prueba, y en otros hilos, se sigue publicando.
    error_publisher.publish_error("REAL", "de producción")
    assert publicados == ["REAL"]


def test_el_silencio_es_solo_del_hilo_de_la_prueba(monkeypatch):
    publicados = []
    monkeypatch.setattr(error_publisher._error_dispatcher, "submit",
                        lambda item: publicados.append(item["error_type"]))

    with error_publisher.suppress_error_publishing():
        otro = threading.Thread(target=error_publisher.publish_error,
                                args=("DEL_SERVICIO", "x"))
        otro.start()
        otro.join()
        error_publisher.publish_error("DE_LA_PRUEBA", "x")

    assert publicados == ["DEL_SERVICIO"]


def test_la_configuracion_del_candidato_no_se_modifica():
    configs = []
    impresora = ImpresoraFalsa(ESTADO_OK)
    original = dict(RED.driver_config)

    def construir_y_mutar(config):
        configs.append(config)
        config["port"] = 9100  # build_driver normaliza tipos sobre su copia
        return BuiltDriver(impresora, "Network", None, config)

    pt.run_print_test(RED, info(RED), builder=construir_y_mutar)

    assert RED.driver_config == original
    assert configs[0] is not RED.driver_config


@pytest.fixture
def configberry_real(monkeypatch, tmp_path):
    from fiscalberry.common.Configberry import Configberry

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    limpio = configparser.ConfigParser()
    limpio.optionxform = str
    monkeypatch.setattr(Configberry, "config", limpio)
    monkeypatch.setattr(Configberry, "_instance", None)
    c = Configberry()
    yield c
    Configberry._instance = None


def test_el_config_ini_no_cambia_durante_la_prueba(configberry_real, monkeypatch):
    ruta = configberry_real.getConfigFIle()
    antes = open(ruta, "rb").read()
    monkeypatch.setattr(type(configberry_real), "set",
                        lambda *a, **k: pytest.fail("la prueba no escribe el config"))

    # Un puerto que seguro está cerrado: se toma uno libre y se suelta.
    libre = socket.socket()
    libre.bind(("127.0.0.1", 0))
    puerto = libre.getsockname()[1]
    libre.close()
    candidato = PrinterCandidate.network("127.0.0.1", puerto)
    # Driver real, sin impresora: la prueba falla, y lo que importa es el config.
    resultado = pt.run_print_test(candidato, info(candidato), status_timeout=0.5)

    assert resultado.technical_success is False
    assert open(ruta, "rb").read() == antes


def test_solo_se_guarda_con_exito_tecnico_y_papel_confirmado():
    class ConfigFalso:
        def __init__(self):
            self.data, self.writes = {}, []

        def get_actual_config(self):
            return {s: dict(v) for s, v in self.data.items()}

        def set(self, section, values):
            self.writes.append(section)
            self.data[section] = dict(values)
            return True

    config = ConfigFalso()
    service = PrinterSetupService(config)
    resultado = pt.run_print_test(RED, info(RED), builder=constructor(ImpresoraFalsa(ESTADO_OK)))

    with pytest.raises(Exception):
        service.save_confirmed("Cocina", RED, technical_success=resultado.technical_success,
                               physical_confirmed=resultado.paper_confirmed)
    assert config.writes == []

    resultado.confirm_paper(True)
    service.save_confirmed("Cocina", RED, technical_success=resultado.technical_success,
                           physical_confirmed=resultado.paper_confirmed)
    assert config.writes == ["Cocina"]


def test_sin_exito_tecnico_no_se_puede_confirmar_papel():
    resultado = pt.PrintTestResult(technical_success=False, problem=pt.PROBLEM_OFFLINE)
    assert resultado.confirm_paper(True) is False
    assert resultado.can_save is False


# ---------------------------------------------------------------------------
# build_driver: el mismo camino que producción
# ---------------------------------------------------------------------------

def test_build_driver_trabaja_sobre_una_copia():
    config = {"driver": "Network", "host": "192.168.1.80", "port": "9100",
              "timeout": "10", "_setup_id": "network:192.168.1.80:9100"}
    original = dict(config)

    construido = build_driver(config)

    assert config == original
    assert construido.name == "Network"
    assert construido.driver.port == 9100
    assert construido.driver.timeout == 10.0
    assert "_setup_id" not in construido.options


def test_build_driver_tipa_los_parametros_del_puerto_serie():
    """pyserial no acepta texto: el config.ini guardaba "8" y el COM no abría."""
    pytest.importorskip("serial")
    construido = build_driver({"driver": "Serial", "devfile": "COM3", "baudrate": "19200",
                               "bytesize": "8", "timeout": "1.5", "stopbits": "1",
                               "dsrdtr": "false", "_usb_vid": "0x1a86"})
    driver = construido.driver
    assert (driver.baudrate, driver.bytesize, driver.timeout, driver.stopbits) == (19200, 8, 1.5, 1)
    assert driver.dsrdtr is False


def test_build_driver_con_un_driver_invalido_lo_nombra():
    with pytest.raises(DriverError, match="Invalid driver: impresora-magica"):
        build_driver({"driver": "impresora-magica"})


# ---------------------------------------------------------------------------
# Clasificación de errores
# ---------------------------------------------------------------------------

class ErrorWin(Exception):
    def __init__(self, codigo):
        super().__init__(codigo, "OpenPrinter", "x")
        self.winerror = codigo


@pytest.mark.parametrize("error,problema", [
    (DriverError("no"), pt.PROBLEM_DRIVER),
    (ConnectionRefusedError(), pt.PROBLEM_REFUSED),
    (PermissionError(13, "Permission denied"), pt.PROBLEM_ACCESS_DENIED),
    (socket.timeout(), pt.PROBLEM_TIMEOUT),
    (ErrorWin(5), pt.PROBLEM_ACCESS_DENIED),
    (ErrorWin(1801), pt.PROBLEM_NOT_FOUND),
    (Exception("could not open port 'COM9': FileNotFoundError"), pt.PROBLEM_NOT_FOUND),
    (Exception("could not open port 'COM3': PermissionError(13, 'Access is denied.')"),
     pt.PROBLEM_ACCESS_DENIED),
    (ValueError("otra cosa"), pt.PROBLEM_UNKNOWN),
])
def test_clasificacion_de_errores(error, problema):
    assert pt.classify_error(error) == problema
    assert pt.ACTIONS[problema]
