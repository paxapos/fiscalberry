"""
Ticket de prueba del asistente de impresoras (#172).

Prueba un candidato (printer_setup.PrinterCandidate) por el MISMO camino de
driver que usa producción (ComandosHandler.build_driver), pero sin MQTT y sin
el config.ini: la impresora todavía no está guardada, y no se guarda hasta que
la prueba sale bien Y la persona confirma que el ticket salió en papel.

Dos resultados separados:

- Éxito técnico: los bytes llegaron y la impresora no reportó problemas. En los
  transportes bidireccionales (red, USB directo, COM) se lee el estado real con
  DLE EOT antes y después de imprimir. En una cola de Windows se sigue el
  trabajo con EnumJobs: que el spooler lo acepte no prueba nada, muchas colas
  dicen "Lista" con la impresora apagada.
- Papel confirmado: lo dice la persona mirando el ticket, que trae un código
  corto para saber sin dudas qué impresora imprimió.

Una prueba en una cola de Windows que no se confirma (o que se cancela) se
borra de la cola con SetJob(JOB_CONTROL_DELETE): si no, la impresora podría
imprimirla sola más tarde ("ticket fantasma").

Las pruebas no publican en el topic de errores del backend: una impresora que
todavía no se configuró y falla no es un error de producción.
"""

import copy
import errno
import random
import socket
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.printer_setup import TRANSPORT_USBPRINT, TRANSPORT_WIN32RAW

logger = getLogger("PrinterTest")


# -- Problemas y qué hacer con cada uno ---------------------------------------

PROBLEM_OFFLINE = "fuera_de_linea"
PROBLEM_COVER_OPEN = "tapa_abierta"
PROBLEM_PAPER_OUT = "sin_papel"
PROBLEM_PAPER_NEAR_END = "papel_por_acabarse"   # aviso: no impide guardar
PROBLEM_PRINTER_ERROR = "error_impresora"
PROBLEM_ACCESS_DENIED = "acceso_denegado"
PROBLEM_TIMEOUT = "sin_respuesta"
PROBLEM_NOT_FOUND = "no_encontrada"
PROBLEM_REFUSED = "rechazada"
PROBLEM_JOB_STUCK = "trabajo_sin_imprimir"
PROBLEM_DRIVER = "conexion_no_disponible"
PROBLEM_UNKNOWN = "desconocido"

ACTIONS = {
    PROBLEM_OFFLINE: (
        "La impresora está fuera de línea. Revisá que esté encendida, "
        "con la tapa cerrada y con papel, y probá de nuevo."),
    PROBLEM_COVER_OPEN: (
        "La tapa de la impresora está abierta. Cerrala bien, hasta que haga "
        "clic, y probá de nuevo."),
    PROBLEM_PAPER_OUT: (
        "La impresora no tiene papel. Poné un rollo nuevo, cerrá la tapa y "
        "probá de nuevo."),
    PROBLEM_PAPER_NEAR_END: "Al rollo le queda poco papel: tené uno de repuesto a mano.",
    PROBLEM_PRINTER_ERROR: (
        "La impresora avisó un error. Apagala, esperá diez segundos, "
        "prendela y probá de nuevo."),
    PROBLEM_ACCESS_DENIED: (
        "Windows no dejó usar la impresora. Cerrá otros programas que la "
        "estén usando y probá de nuevo."),
    PROBLEM_TIMEOUT: (
        "La impresora no respondió a tiempo. Revisá que esté encendida y bien "
        "conectada (cable USB o de red) y probá de nuevo."),
    PROBLEM_NOT_FOUND: (
        "No se encontró la impresora. Revisá que esté encendida y conectada "
        "y probá de nuevo."),
    PROBLEM_REFUSED: (
        "En esa dirección responde un equipo, pero no recibe impresiones. "
        "Revisá que sea la impresora."),
    PROBLEM_JOB_STUCK: (
        "Windows recibió el ticket pero la impresora no lo tomó. Revisá que "
        "esté encendida y conectada. La prueba se canceló para que no salga "
        "sola más tarde."),
    PROBLEM_DRIVER: "Este tipo de conexión todavía no está disponible en esta computadora.",
    PROBLEM_UNKNOWN: "No se pudo imprimir la prueba. Revisá la impresora y probá de nuevo.",
}


# -- Estado real por DLE EOT --------------------------------------------------

DLE_EOT = b"\x10\x04"
STATUS_PRINTER = 1        # n=1: estado de la impresora
STATUS_OFFLINE_CAUSE = 2  # n=2: causa de fuera de línea
STATUS_PAPER = 4          # n=4: sensores de papel

# Bits de cada respuesta (ESC/POS, iguales en las Epson TM y compatibles).
_OFFLINE = 0x08           # n=1 bit 3
_COVER_OPEN = 0x04        # n=2 bit 2
_STOPPED_PAPER_END = 0x20  # n=2 bit 5
_ERROR = 0x40             # n=2 bit 6
_PAPER_NEAR_END = 0x0C    # n=4 bits 2 y 3
_PAPER_END = 0x60         # n=4 bits 5 y 6

# Toda respuesta de estado trae bit 1 y bit 4 en 1, y bit 0 y bit 7 en 0.
_FIXED_MASK = 0x93
_FIXED_VALUE = 0x12

# Cuánto se espera cada respuesta. Muchas impresoras de red no contestan DLE
# EOT: no puede costar más que esto averiguarlo.
STATUS_TIMEOUT = 2.0


@dataclass(frozen=True)
class PrinterStatus:
    """Estado leído con DLE EOT. None en un campo = no se sabe."""

    online: Optional[bool] = None
    cover_open: Optional[bool] = None
    paper_out: Optional[bool] = None
    paper_near_end: Optional[bool] = None
    error: Optional[bool] = None

    @property
    def known(self):
        """Si la impresora contestó (muchas por red no lo hacen)."""
        return self.online is not None

    @property
    def blocking_problem(self):
        """Lo que impide imprimir, en el orden en que conviene resolverlo."""
        if self.cover_open:
            return PROBLEM_COVER_OPEN
        if self.paper_out:
            return PROBLEM_PAPER_OUT
        if self.online is False:
            return PROBLEM_OFFLINE
        if self.error:
            return PROBLEM_PRINTER_ERROR
        return None

    @property
    def warning(self):
        if self.paper_near_end and not self.paper_out:
            return PROBLEM_PAPER_NEAR_END
        return None

    def as_dict(self):
        return {
            "online": self.online,
            "cover_open": self.cover_open,
            "paper_out": self.paper_out,
            "paper_near_end": self.paper_near_end,
            "error": self.error,
        }


UNKNOWN_STATUS = PrinterStatus()


def status_byte(response):
    """El byte de estado de una respuesta DLE EOT, o None si no la hay."""
    for valor in bytes(response or b""):
        if valor & _FIXED_MASK == _FIXED_VALUE:
            return valor
    return None


def parse_status(printer, offline_cause=None, paper=None):
    """Arma un PrinterStatus a partir de los bytes de n=1, n=2 y n=4."""
    if printer is None:
        return UNKNOWN_STATUS
    online = not (printer & _OFFLINE)
    cover_open = paper_out = error = paper_near_end = None
    if offline_cause is not None:
        cover_open = bool(offline_cause & _COVER_OPEN)
        paper_out = bool(offline_cause & _STOPPED_PAPER_END)
        error = bool(offline_cause & _ERROR)
    if paper is not None:
        paper_out = bool(paper & _PAPER_END) or bool(paper_out)
        paper_near_end = bool(paper & _PAPER_NEAR_END)
    return PrinterStatus(online=online, cover_open=cover_open, paper_out=paper_out,
                         paper_near_end=paper_near_end, error=error)


@contextmanager
def _short_read_timeout(driver, seconds):
    """
    Acorta la espera de lectura mientras se consulta el estado: el driver de
    red se guarda con 10 s de timeout, y una impresora que no contesta DLE EOT
    haría esperar eso por cada consulta.
    """
    dispositivo = driver.device  # abre la conexión si hacía falta (puede lanzar)
    anterior = None
    try:
        if hasattr(dispositivo, "gettimeout") and hasattr(dispositivo, "settimeout"):
            anterior = ("socket", dispositivo.gettimeout())
            dispositivo.settimeout(seconds)
        elif dispositivo is not None and hasattr(dispositivo, "timeout"):
            anterior = ("serial", dispositivo.timeout)
            dispositivo.timeout = seconds
    except Exception:
        anterior = None
    try:
        yield
    finally:
        try:
            if anterior and anterior[0] == "socket":
                dispositivo.settimeout(anterior[1])
            elif anterior:
                dispositivo.timeout = anterior[1]
        except Exception:
            pass


def _query(driver, n):
    """
    Una consulta DLE EOT. Devuelve el byte de estado, o None si la impresora
    no contesta. Un error al ENVIAR se propaga: es un problema de conexión.
    """
    driver._raw(DLE_EOT + bytes([n]))
    try:
        return status_byte(driver._read())
    except (NotImplementedError, socket.timeout, TimeoutError):
        return None
    except OSError as e:
        logger.debug(f"Sin respuesta de estado (DLE EOT {n}): {e}")
        return None


def read_status(driver, timeout=STATUS_TIMEOUT):
    """
    Lee el estado real (DLE EOT 1, 2 y 4). Si la impresora no contesta
    devuelve UNKNOWN_STATUS: no es un error, muchas no lo soportan por red.
    """
    with _short_read_timeout(driver, timeout):
        printer = _query(driver, STATUS_PRINTER)
        if printer is None:
            return UNKNOWN_STATUS
        offline_cause = _query(driver, STATUS_OFFLINE_CAUSE)
        paper = _query(driver, STATUS_PAPER)
    return parse_status(printer, offline_cause, paper)


# -- Cola de Windows ----------------------------------------------------------

# Constantes de winspool.h (win32print las expone, pero así se prueba sin él).
JOB_STATUS_PAUSED = 0x00000001
JOB_STATUS_ERROR = 0x00000002
JOB_STATUS_DELETING = 0x00000004
JOB_STATUS_SPOOLING = 0x00000008
JOB_STATUS_PRINTING = 0x00000010
JOB_STATUS_OFFLINE = 0x00000020
JOB_STATUS_PAPEROUT = 0x00000040
JOB_STATUS_PRINTED = 0x00000080
JOB_STATUS_DELETED = 0x00000100
JOB_STATUS_BLOCKED_DEVQ = 0x00000200
JOB_STATUS_USER_INTERVENTION = 0x00000400
JOB_STATUS_COMPLETE = 0x00001000
JOB_CONTROL_DELETE = 5

JOB_DONE = "terminado"
JOB_PENDING = "en_cola"
JOB_FAILED = "con_error"

# Cuánto se espera que el trabajo salga de la cola.
JOB_TIMEOUT = 15.0


class Win32JobTracker:
    """Sigue el trabajo de prueba en la cola de Windows y lo borra si hace falta."""

    POLL_SECONDS = 0.5

    def __init__(self, printer_name, job_id, win32print=None):
        self.printer_name = printer_name
        self.job_id = job_id
        self._w = win32print
        self.last_state = JOB_PENDING

    def _api(self):
        if self._w is None:
            import win32print
            self._w = win32print
        return self._w

    def status(self):
        """(estado, problema) del trabajo según EnumJobs."""
        w = self._api()
        handle = w.OpenPrinter(self.printer_name)
        try:
            trabajos = w.EnumJobs(handle, 0, -1, 1) or []
        finally:
            w.ClosePrinter(handle)

        trabajo = next((t for t in trabajos if t.get("JobId") == self.job_id), None)
        if trabajo is None:
            return JOB_DONE, None  # salió de la cola: el puerto lo entregó
        estado = int(trabajo.get("Status") or 0)
        if estado & (JOB_STATUS_PRINTED | JOB_STATUS_COMPLETE
                     | JOB_STATUS_DELETED | JOB_STATUS_DELETING):
            return JOB_DONE, None
        if estado & JOB_STATUS_PAPEROUT:
            return JOB_FAILED, PROBLEM_PAPER_OUT
        if estado & (JOB_STATUS_OFFLINE | JOB_STATUS_PAUSED):
            return JOB_FAILED, PROBLEM_OFFLINE
        if estado & (JOB_STATUS_ERROR | JOB_STATUS_BLOCKED_DEVQ | JOB_STATUS_USER_INTERVENTION):
            return JOB_FAILED, PROBLEM_PRINTER_ERROR
        return JOB_PENDING, None

    def wait(self, timeout=JOB_TIMEOUT, clock=time.monotonic, sleep=time.sleep):
        """Espera a que el trabajo salga de la cola o falle."""
        limite = clock() + timeout
        while True:
            estado, problema = self.status()
            self.last_state = estado
            if estado != JOB_PENDING:
                return estado, problema
            if clock() >= limite:
                return JOB_PENDING, PROBLEM_JOB_STUCK
            sleep(self.POLL_SECONDS)

    def cancel(self):
        """
        Borra el trabajo si sigue en la cola. Devuelve True si ya no queda
        nada pendiente (borrado, o ya había salido).
        """
        try:
            estado, _ = self.status()
            if estado == JOB_DONE:
                self.last_state = JOB_DONE
                return True
            w = self._api()
            handle = w.OpenPrinter(self.printer_name)
            try:
                w.SetJob(handle, self.job_id, 0, None, JOB_CONTROL_DELETE)
            finally:
                w.ClosePrinter(handle)
            self.last_state = JOB_DONE
            logger.info("Prueba cancelada en la cola '%s' (trabajo %s)",
                        self.printer_name, self.job_id)
            return True
        except Exception as e:
            logger.warning("No se pudo borrar la prueba de la cola '%s': %s",
                           self.printer_name, e)
            return False


# -- El ticket ----------------------------------------------------------------

# Sin caracteres que se confunden al leerlos en papel (0/O, 1/I/L, 2/Z, 5/S, 8/B).
_CODE_ALPHABET = "ACDEFGHJKMNPQRTUVWXY34679"
CODE_LENGTH = 4


def new_test_code(rng=None):
    rng = rng or random.SystemRandom()
    return "".join(rng.choice(_CODE_ALPHABET) for _ in range(CODE_LENGTH))


@dataclass(frozen=True)
class PrintTestInfo:
    """Lo que va impreso para reconocer sin dudas qué impresora imprimió."""

    commerce: str
    alias: str
    connection: str
    code: str
    moment: datetime

    @classmethod
    def for_candidate(cls, candidate, commerce="", alias="", code=None, now=None):
        return cls(
            commerce=commerce or "Sin comercio",
            alias=alias or candidate.display_name,
            connection=candidate.connection_label,
            code=code or new_test_code(),
            moment=now or datetime.now(),
        )


def render_test_ticket(driver, info):
    driver.set(align="center", bold=True, double_height=True, double_width=True)
    driver.textln("PRUEBA")
    driver.textln(info.code)
    driver.set(align="center", bold=False, normal_textsize=True)
    driver.textln("Fiscalberry - ticket de prueba")
    driver.textln("")
    driver.set(align="left", normal_textsize=True)
    driver.textln(f"Comercio: {info.commerce}")
    driver.textln(f"Impresora: {info.alias}")
    driver.textln(f"Conexion: {info.connection}")
    driver.textln(f"Hora: {info.moment:%d/%m/%Y %H:%M:%S}")
    driver.textln("")
    driver.set(align="center", normal_textsize=True)
    driver.textln("Si ves este ticket, la impresora")
    driver.textln("funciona. Confirmalo en la pantalla")
    driver.textln(f"con el codigo {info.code}.")
    driver.cut()


# -- Resultado -----------------------------------------------------------------

@dataclass
class PrintTestResult:
    technical_success: bool
    problem: Optional[str] = None
    detail: str = ""
    status_before: PrinterStatus = UNKNOWN_STATUS
    status_after: PrinterStatus = UNKNOWN_STATUS
    warning: Optional[str] = None
    job_cancelled: bool = False
    paper_confirmed: bool = False
    tracker: Optional[Win32JobTracker] = field(default=None, repr=False)
    # Estado LPT de usbprint (#183): solo informativo, nunca decide la prueba.
    lpt_status: dict = field(default_factory=dict)

    @property
    def action(self):
        """Qué tiene que hacer la persona, en palabras."""
        return ACTIONS.get(self.problem) if self.problem else None

    @property
    def can_save(self):
        return self.technical_success and self.paper_confirmed

    def confirm_paper(self, printed):
        """
        La persona dice si el ticket salió en papel. Sin éxito técnico no hay
        nada que confirmar; si dice que no salió, lo pendiente se cancela.
        """
        self.paper_confirmed = bool(printed) and self.technical_success
        if not printed:
            self.cancel()
        return self.paper_confirmed

    def cancel(self):
        """Se abandona la prueba: lo que haya quedado en la cola se borra."""
        if self.tracker is not None and not self.job_cancelled:
            self.job_cancelled = self.tracker.cancel()
        return self.job_cancelled


def _failed(problem, detail="", **kwargs):
    return PrintTestResult(technical_success=False, problem=problem, detail=detail, **kwargs)


# -- Clasificación de errores --------------------------------------------------

_ACCESS_DENIED_WINERRORS = {5, 32, 170}  # acceso denegado, archivo en uso, ocupado
# no existe, ruta, nombre de impresora inválido; USB desenchufada (#183):
# dispositivo no conectado, no existe, falla general del dispositivo.
_NOT_FOUND_WINERRORS = {2, 3, 1801, 1167, 433, 31}
_TIMEOUT_WINERRORS = {121, 1460}
_ACCESS_DENIED_TEXT = ("access is denied", "acceso denegado", "permission denied",
                       "being used by another process")
_TIMEOUT_TEXT = ("timed out", "timeout", "tiempo de espera")


def _cadena(error):
    visto = set()
    while error is not None and id(error) not in visto:
        visto.add(id(error))
        yield error
        error = error.__cause__ or error.__context__


def classify_error(error):
    """El problema (PROBLEM_*) que explica una excepción de la prueba."""
    from fiscalberry.common.ComandosHandler import DriverError

    for e in _cadena(error):
        if isinstance(e, DriverError):
            return PROBLEM_DRIVER
        if isinstance(e, ConnectionRefusedError):
            return PROBLEM_REFUSED
        if isinstance(e, PermissionError):
            return PROBLEM_ACCESS_DENIED
        if isinstance(e, (socket.timeout, TimeoutError)):
            return PROBLEM_TIMEOUT
        winerror = getattr(e, "winerror", None)
        if winerror is None and getattr(e, "args", None) and isinstance(e.args[0], int) \
                and type(e).__name__ == "error":
            winerror = e.args[0]  # pywintypes.error: (código, función, mensaje)
        if winerror in _ACCESS_DENIED_WINERRORS:
            return PROBLEM_ACCESS_DENIED
        if winerror in _NOT_FOUND_WINERRORS:
            return PROBLEM_NOT_FOUND
        if winerror in _TIMEOUT_WINERRORS:
            return PROBLEM_TIMEOUT
        if isinstance(e, OSError) and e.errno in (errno.EHOSTUNREACH, errno.ENETUNREACH,
                                                  errno.ENOENT, errno.ENODEV):
            return PROBLEM_NOT_FOUND

    texto = " ".join(str(e) for e in _cadena(error)).lower()
    if any(t in texto for t in _ACCESS_DENIED_TEXT):
        return PROBLEM_ACCESS_DENIED
    if any(t in texto for t in _TIMEOUT_TEXT):
        return PROBLEM_TIMEOUT
    if type(error).__name__ == "DeviceNotFoundError" or "could not open" in texto:
        return PROBLEM_NOT_FOUND
    return PROBLEM_UNKNOWN


# -- La prueba -----------------------------------------------------------------

def _cerrar(driver):
    try:
        driver.close()
    except Exception as e:
        logger.debug(f"Error cerrando el driver de prueba: {e}")


def run_print_test(candidate, info, builder=None, tracker_factory=None,
                   job_timeout=JOB_TIMEOUT, status_timeout=STATUS_TIMEOUT):
    """
    Imprime el ticket de prueba de `candidate` y devuelve un PrintTestResult.

    No lanza: todo error queda clasificado en el resultado, con su acción. No
    toca el config.ini ni publica errores. Bloquea (red, USB, cola de Windows):
    la interfaz tiene que llamarla desde un hilo aparte.
    """
    from fiscalberry.common.ComandosHandler import build_driver
    from fiscalberry.common.rabbitmq.error_publisher import suppress_error_publishing

    # Copia: el driver normaliza tipos sobre su configuración, y el candidato
    # se sigue usando después (para guardarlo, o para otra prueba).
    config = copy.deepcopy(candidate.driver_config)

    with suppress_error_publishing():
        try:
            driver = (builder or build_driver)(config).driver
        except Exception as e:
            logger.info("Prueba de '%s': no se pudo crear el driver: %s", info.alias, e)
            return _failed(classify_error(e), str(e))

        tracker = None
        try:
            antes = UNKNOWN_STATUS
            if candidate.status_readable:
                antes = read_status(driver, status_timeout)
                if antes.blocking_problem:
                    return _failed(antes.blocking_problem, status_before=antes)

            render_test_ticket(driver, info)

            if candidate.transport == TRANSPORT_WIN32RAW:
                job_id = getattr(driver, "current_job", None)
                # EndDocPrinter: recién ahí el trabajo queda completo en la cola.
                _cerrar(driver)
                if not job_id:
                    return _failed(PROBLEM_UNKNOWN, "Windows no informó el trabajo de prueba")
                tracker = (tracker_factory or Win32JobTracker)(
                    config.get("printer_name", ""), job_id)
                estado, problema = tracker.wait(job_timeout)
                if estado != JOB_DONE:
                    # Que no salga sola más tarde: se borra ya.
                    cancelado = tracker.cancel()
                    return _failed(problema or PROBLEM_JOB_STUCK, tracker=tracker,
                                   job_cancelled=cancelado)

            despues = UNKNOWN_STATUS
            if candidate.status_readable:
                despues = read_status(driver, status_timeout)
                if despues.blocking_problem:
                    return _failed(despues.blocking_problem, status_before=antes,
                                   status_after=despues)

            lpt = {}
            if candidate.transport == TRANSPORT_USBPRINT and hasattr(driver, "lpt_status"):
                try:
                    lpt = driver.lpt_status() or {}
                except Exception:
                    lpt = {}
            return PrintTestResult(
                technical_success=True,
                status_before=antes,
                status_after=despues,
                warning=despues.warning or antes.warning,
                tracker=tracker,
                lpt_status=lpt,
            )
        except Exception as e:
            problema = classify_error(e)
            logger.info("Prueba de '%s' fallida (%s): %s", info.alias, problema, e)
            if tracker is not None:
                tracker.cancel()
            return _failed(problema, str(e), tracker=tracker)
        finally:
            _cerrar(driver)
