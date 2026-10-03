# coding=utf-8
"""
Ticket de prueba del asistente (#172).

Lo que fijan estos tests:

- El ticket dice comercio, impresora, conexión, hora y un código corto: con dos
  térmicas al lado tiene que quedar claro cuál se probó.
- La prueba usa el mismo driver que producción (build_driver), sin escribir
  config.ini y sin publicar errores al backend.
- Fuera de línea, sin papel, tapa abierta, acceso denegado y timeout terminan en
  una acción concreta para la persona. Una impresora que no contesta la
  consulta de estado NO es una impresora fuera de línea.
- En una cola de Windows, que el spooler acepte el trabajo no es éxito: se lo
  sigue, y si no se confirma en papel se lo borra (sin "ticket fantasma").
- Sin éxito técnico Y confirmación en papel no se guarda nada.
"""

import errno
import socket
import threading
from datetime import datetime

import pytest
from escpos import printer

from fiscalberry.common import printer_setup as ps
from fiscalberry.common import ticket_prueba as tp
from fiscalberry.common.printer_setup import PrinterCandidate, PrinterSetupService

AHORA = datetime(2026, 10, 3, 14, 5)
DLE_EOT_1, DLE_EOT_2, DLE_EOT_4 = b"\x10\x04\x01", b"\x10\x04\x02", b"\x10\x04\x04"

# Respuestas reales de una térmica Epson (los bits fijos 0x12 siempre van).
OK = {DLE_EOT_1: b"\x12", DLE_EOT_2: b"\x12", DLE_EOT_4: b"\x12"}


class DriverConEstado(printer.Dummy):
    """Una impresora que contesta DLE EOT con lo que le digan."""

    def __init__(self, respuestas=None, despues=None, **kwargs):
        super().__init__(**kwargs)
        self.respuestas = respuestas
        self.despues = despues      # respuestas después de imprimir
        self._ultima = None
        self.impreso = False
        self.cerrado = False

    def _raw(self, msg):
        if msg in (DLE_EOT_1, DLE_EOT_2, DLE_EOT_4):
            self._ultima = msg
            return
        self.impreso = True
        super()._raw(msg)

    def _read(self):
        respuestas = self.despues if (self.impreso and self.despues) else self.respuestas
        if respuestas is None:
            raise NotImplementedError()
        return respuestas.get(self._ultima, b"")

    def close(self):
        self.cerrado = True


def _red():
    return PrinterCandidate.network("192.168.1.80", 9100)


def _probar(candidato, driver, **kwargs):
    return tp.probar(candidato, "Cocina", comercio="Pizzeria Don Pepe", codigo="K7QX",
                     ahora=AHORA, crear_driver=lambda conf: (driver, "x", {}, None),
                     **kwargs)


# --------------------------------------------------------------------------
# El ticket
# --------------------------------------------------------------------------

def test_el_ticket_identifica_la_impresora_y_trae_un_codigo():
    contenido = tp.contenido_del_ticket(_red(), "Cocina", "Pizzería Don Pepe", "K7QX", AHORA)

    assert contenido["titulo"] == "PRUEBA DE IMPRESORA"
    assert contenido["lineas"] == [
        "Comercio: Pizzería Don Pepe",
        "Impresora: Cocina",
        "Conexión: Red (Puerto 9100)",
        "Fecha: 03/10/2026 14:05",
    ]
    assert contenido["codigo"] == "K7QX"


def test_lo_impreso_trae_el_codigo_y_se_corta():
    driver = DriverConEstado(OK)
    resultado = _probar(_red(), driver)

    salida = driver.output
    assert b"K7QX" in salida
    assert b"Impresora: Cocina" in salida
    assert b"Fecha: 03/10/2026 14:05" in salida
    assert b"\x1dV" in salida            # corte de papel
    assert resultado.codigo == "K7QX"
    assert driver.cerrado


def test_los_codigos_no_tienen_caracteres_que_se_confundan():
    codigos = {tp.nuevo_codigo() for _ in range(200)}
    assert all(len(c) == tp.LARGO_CODIGO for c in codigos)
    assert not set("".join(codigos)) & set("01258BGIOQSZL6")
    assert len(codigos) > 150


# --------------------------------------------------------------------------
# Estado real (DLE EOT)
# --------------------------------------------------------------------------

def test_impresora_en_linea_sale_bien():
    resultado = _probar(_red(), DriverConEstado(OK))

    assert resultado.exito_tecnico
    assert resultado.problema is None
    assert resultado.estado_antes.responde and resultado.estado_despues.responde


@pytest.mark.parametrize("respuestas,problema,palabra", [
    ({**OK, DLE_EOT_2: b"\x16"}, tp.TAPA_ABIERTA, "tapa"),          # bit 2
    ({**OK, DLE_EOT_4: b"\x72"}, tp.SIN_PAPEL, "papel"),            # sensor sin papel
    ({**OK, DLE_EOT_2: b"\x32"}, tp.SIN_PAPEL, "papel"),            # paró por fin de papel
    ({**OK, DLE_EOT_2: b"\x52"}, tp.ERROR_IMPRESORA, "error"),      # bit 6
    ({**OK, DLE_EOT_1: b"\x1a"}, tp.FUERA_DE_LINEA, "fuera de línea"),  # bit 3
])
def test_problemas_antes_de_imprimir_no_imprimen_y_dicen_que_hacer(respuestas, problema, palabra):
    driver = DriverConEstado(respuestas)
    resultado = _probar(_red(), driver)

    assert not resultado.exito_tecnico
    assert resultado.problema == problema
    assert palabra in resultado.accion.lower()
    assert not driver.impreso
    assert driver.cerrado


def test_un_problema_que_aparece_al_imprimir_tambien_cuenta():
    """Se terminó el papel justo con la prueba."""
    resultado = _probar(_red(), DriverConEstado(OK, despues={**OK, DLE_EOT_4: b"\x72"}))
    assert not resultado.exito_tecnico
    assert resultado.problema == tp.SIN_PAPEL


def test_papel_por_acabarse_sale_bien_pero_avisa():
    resultado = _probar(_red(), DriverConEstado(OK, despues={**OK, DLE_EOT_4: b"\x1e"}))
    assert resultado.exito_tecnico
    assert resultado.avisos == [tp.AVISO_PAPEL_POR_ACABARSE]


def test_si_no_contesta_el_estado_no_es_fuera_de_linea():
    """Muchas impresoras no contestan DLE EOT: eso es "no se sabe"."""
    driver = DriverConEstado(respuestas=None)
    resultado = _probar(_red(), driver)

    assert resultado.exito_tecnico
    assert resultado.estado_antes.responde is False
    assert driver.impreso


def test_la_cola_de_windows_no_consulta_estado():
    """El spooler es unidireccional: no se le puede preguntar."""
    driver = DriverConEstado(respuestas={DLE_EOT_1: b"\x1a"})   # "fuera de línea"
    candidato = PrinterCandidate.windows_queue("EPSON")
    resultado = _probar(candidato, driver)

    assert resultado.estado_antes is None
    assert driver.impreso


# --------------------------------------------------------------------------
# Errores con acción concreta
# --------------------------------------------------------------------------

class PywintypesError(Exception):
    """Como pywintypes.error: (código, función, mensaje). No es un OSError."""


def _envuelto(causa, mensaje="Could not open socket for 192.168.1.80"):
    """python-escpos lanza DeviceNotFoundError dentro del except de la causa."""
    from escpos.exceptions import DeviceNotFoundError
    try:
        raise causa
    except BaseException:
        try:
            raise DeviceNotFoundError(mensaje)
        except DeviceNotFoundError as e:
            return e


@pytest.mark.parametrize("error,problema", [
    (_envuelto(ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")), tp.RECHAZADA),
    (_envuelto(socket.timeout("timed out")), tp.TIMEOUT),
    (_envuelto(OSError(errno.EHOSTUNREACH, "No route to host")), tp.NO_RESPONDE),
    # Windows en español: el texto viene traducido, el código no.
    (_envuelto(OSError(10061, "No se puede establecer una conexión ya que el equipo "
                              "de destino denegó expresamente dicha conexión")), tp.RECHAZADA),
    (_envuelto(PywintypesError(5, "OpenPrinter", "Acceso denegado."),
               "Unable to start a print job for the printer EPSON"), tp.ACCESO_DENEGADO),
    (_envuelto(AssertionError("Incorrect printer name"),
               "Unable to start a print job for the printer EPSON"), tp.NO_ENCONTRADA),
    (Exception("could not open port 'COM3': PermissionError(13, 'Acceso denegado.', None, 5)"),
     tp.ACCESO_DENEGADO),
    (Exception("could not open port 'COM9': FileNotFoundError(2, 'El sistema no puede "
               "encontrar el archivo especificado.', None, 2)"), tp.NO_ENCONTRADA),
    (ValueError("algo raro"), tp.ERROR),
])
def test_clasificacion_de_errores(error, problema):
    assert tp.clasificar_error(error) == problema


def test_en_linux_el_codigo_5_no_es_acceso_denegado():
    assert tp.clasificar_error(OSError(5, "Input/output error")) == tp.ERROR


@pytest.mark.parametrize("problema", [
    tp.FUERA_DE_LINEA, tp.SIN_PAPEL, tp.TAPA_ABIERTA, tp.ACCESO_DENEGADO,
    tp.TIMEOUT, tp.NO_RESPONDE, tp.NO_ENCONTRADA, tp.RECHAZADA, tp.EN_COLA,
])
def test_cada_problema_tiene_una_accion_sin_jerga(problema):
    accion = tp.ACCIONES[problema]
    assert accion
    for jerga in ("DLE", "EOT", "socket", "errno", "spooler", "TCP", "driver"):
        assert jerga not in accion


def test_si_no_se_puede_crear_el_driver_no_explota():
    def roto(conf):
        raise _envuelto(ConnectionRefusedError(errno.ECONNREFUSED, "refused"))

    resultado = tp.probar(_red(), "Cocina", crear_driver=roto)
    assert not resultado.exito_tecnico
    assert resultado.problema == tp.RECHAZADA


# --------------------------------------------------------------------------
# Cola de Windows: seguir el trabajo y no dejar tickets fantasma
# --------------------------------------------------------------------------

class Win32PrintFalso:
    """Una cola con trabajos. `estados` es la secuencia de Status de cada consulta."""

    def __init__(self, estados):
        self.estados = list(estados)
        self.en_cola = True
        self.borrados = []

    def OpenPrinter(self, nombre):
        return ("h", nombre)

    def ClosePrinter(self, handle):
        pass

    def GetJob(self, handle, job_id, level):
        if not self.en_cola:
            raise PywintypesError(87, "GetJob", "El parámetro no es correcto.")
        estado = self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]
        if estado is None:
            self.en_cola = False
            raise PywintypesError(87, "GetJob", "El parámetro no es correcto.")
        return {"JobId": job_id, "Status": estado}

    def SetJob(self, handle, job_id, level, info, command):
        assert command == tp.JOB_CONTROL_DELETE
        self.borrados.append((handle[1], job_id))
        self.en_cola = False


class DriverWin32Falso(DriverConEstado):
    def __init__(self):
        super().__init__(respuestas=None)
        self.current_job = 42


def _probar_cola(w32, espera_cola=1.0):
    candidato = PrinterCandidate.windows_queue("EPSON TM-T20")
    return tp.probar(candidato, "Cocina", codigo="K7QX", ahora=AHORA,
                     crear_driver=lambda conf: (DriverWin32Falso(), "Win32Raw", {}, None),
                     win32print=w32, espera_cola=espera_cola)


def test_el_trabajo_salio_de_la_cola_es_exito_tecnico():
    w32 = Win32PrintFalso([0x8, None])     # JOB_STATUS_SPOOLING, después sale de la cola
    resultado = _probar_cola(w32)

    assert resultado.exito_tecnico
    assert resultado.trabajo.job_id == 42
    assert w32.borrados == []


def test_trabado_en_la_cola_no_es_exito_y_se_borra_ya():
    """La impresora está apagada: el spooler lo aceptó, pero no sale."""
    w32 = Win32PrintFalso([0x8])        # JOB_STATUS_SPOOLING, para siempre
    resultado = _probar_cola(w32, espera_cola=0.3)

    assert not resultado.exito_tecnico
    assert resultado.problema == tp.EN_COLA
    # Si quedara, saldría solo cuando la prendan: un ticket fantasma.
    assert w32.borrados == [("EPSON TM-T20", 42)]


@pytest.mark.parametrize("estado,problema", [
    (tp.JOB_STATUS_PAPEROUT, tp.SIN_PAPEL),
    (tp.JOB_STATUS_OFFLINE, tp.FUERA_DE_LINEA),
    (tp.JOB_STATUS_ERROR, tp.EN_COLA),
])
def test_estados_del_trabajo_con_accion(estado, problema):
    w32 = Win32PrintFalso([estado])
    resultado = _probar_cola(w32)

    assert resultado.problema == problema
    assert w32.borrados == [("EPSON TM-T20", 42)]


def test_no_salio_en_papel_borra_lo_que_quede_en_la_cola():
    """Impresoras que guardan los trabajos impresos: sigue en la cola, como PRINTED."""
    w32 = Win32PrintFalso([tp.JOB_STATUS_PRINTED])
    resultado = _probar_cola(w32)
    assert resultado.exito_tecnico

    config = _ConfigFalso()
    guardada = tp.finalizar(PrinterSetupService(config), "Cocina",
                            PrinterCandidate.windows_queue("EPSON TM-T20"), resultado,
                            salio_en_papel=False)

    assert guardada is None
    assert w32.borrados == [("EPSON TM-T20", 42)]
    assert config.writes == []


# --------------------------------------------------------------------------
# Confirmar y guardar
# --------------------------------------------------------------------------

class _ConfigFalso:
    def __init__(self):
        self.writes = []

    def get_actual_config(self):
        return {}

    def set(self, section, values):
        self.writes.append((section, dict(values)))
        return True


def test_con_exito_tecnico_y_confirmacion_se_guarda():
    candidato = _red()
    resultado = _probar(candidato, DriverConEstado(OK))
    config = _ConfigFalso()

    assert tp.finalizar(PrinterSetupService(config), "Cocina", candidato, resultado,
                        salio_en_papel=True) == "Cocina"
    assert config.writes[0][1]["_setup_id"] == candidato.stable_id


def test_sin_exito_tecnico_no_se_guarda_aunque_digan_que_salio():
    candidato = _red()
    resultado = _probar(candidato, DriverConEstado({**OK, DLE_EOT_2: b"\x16"}))
    config = _ConfigFalso()

    assert tp.finalizar(PrinterSetupService(config), "Cocina", candidato, resultado,
                        salio_en_papel=True) is None
    assert config.writes == []


# --------------------------------------------------------------------------
# Con el driver de producción
# --------------------------------------------------------------------------

def test_usa_build_driver_sin_tocar_config_ini_ni_publicar_errores(monkeypatch):
    from fiscalberry.common import ComandosHandler as CH
    from fiscalberry.common.Configberry import Configberry

    def prohibido(*a, **kw):
        raise AssertionError("la prueba del asistente no puede hacer esto")

    monkeypatch.setattr(CH, "publish_error", prohibido)
    monkeypatch.setattr(CH.PrinterErrorDetector, "detect_and_publish_error", prohibido)
    monkeypatch.setattr(Configberry, "set", prohibido)

    candidato = PrinterCandidate(display_name="Prueba", connection=ps.USB, stable_id="x",
                                 driver_config={"driver": "Dummy", "_setup_id": "x"},
                                 capacidades={"status_readable": False})
    original = dict(candidato.driver_config)

    resultado = tp.probar(candidato, "Cocina", codigo="K7QX", ahora=AHORA)

    assert resultado.exito_tecnico
    # La configuración del candidato no se mutó (build_driver trabaja con una copia).
    assert candidato.driver_config == original


def _puerto_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()
    return puerto


def test_red_real_impresora_apagada():
    """build_driver + python-escpos de verdad contra un puerto cerrado."""
    candidato = PrinterCandidate.network("127.0.0.1", _puerto_libre())
    resultado = tp.probar(candidato, "Barra", codigo="K7QX", ahora=AHORA, espera_estado=0.5)

    assert not resultado.exito_tecnico
    assert resultado.problema == tp.RECHAZADA


class ImpresoraDeRed:
    """Un servidor TCP que se comporta como una térmica en el puerto 9100."""

    def __init__(self, contesta_estado=True):
        self.contesta_estado = contesta_estado
        self.recibido = b""
        self.servidor = socket.socket()
        self.servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.servidor.bind(("127.0.0.1", 0))
        self.servidor.listen(1)
        self.puerto = self.servidor.getsockname()[1]
        self.hilo = threading.Thread(target=self._atender, daemon=True)
        self.hilo.start()

    def _atender(self):
        conexion, _ = self.servidor.accept()
        conexion.settimeout(5)
        with conexion:
            while True:
                try:
                    datos = conexion.recv(4096)
                except OSError:
                    break
                if not datos:
                    break
                self.recibido += datos
                if self.contesta_estado:
                    for consulta in (DLE_EOT_1, DLE_EOT_2, DLE_EOT_4):
                        if datos.endswith(consulta):
                            conexion.sendall(b"\x12")

    def cerrar(self):
        self.servidor.close()


@pytest.mark.parametrize("contesta_estado", [True, False])
def test_red_real_impresora_encendida(contesta_estado):
    impresora = ImpresoraDeRed(contesta_estado)
    try:
        candidato = PrinterCandidate.network("127.0.0.1", impresora.puerto)
        resultado = tp.probar(candidato, "Barra", comercio="Demo", codigo="K7QX",
                              ahora=AHORA, espera_estado=0.5)
        impresora.hilo.join(5)
    finally:
        impresora.cerrar()

    assert resultado.exito_tecnico, resultado.detalle
    assert resultado.estado_antes.responde is contesta_estado
    assert b"K7QX" in impresora.recibido
