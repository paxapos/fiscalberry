"""
Ticket de prueba del asistente de impresoras (#172).

Antes de guardar una impresora, se le imprime un ticket de prueba por el MISMO
camino de driver que usa después en producción (ComandosHandler.build_driver),
pero sin tocar config.ini, sin pasar por MQTT y sin publicar errores en el topic
del backend: una prueba que falla es parte normal del asistente, no un error
del comercio.

Se separan dos cosas que no son lo mismo:

- Éxito técnico: el ticket se mandó y la impresora no reportó problemas.
- Confirmación en papel: la persona VIO salir el ticket. Esa la pide la
  interfaz, y recién con las dos se guarda (ver PrinterSetupService).

El ticket trae un código corto para que no haya dudas de qué impresora se probó
(con dos térmicas al lado, no alcanza con "salió un ticket").

Por transporte:

- Red, USB directo y COM pueden leer el estado real (DLE EOT) antes y después
  de imprimir: fuera de línea, tapa abierta, sin papel, papel por acabarse.
  Muchas impresoras no contestan esa consulta: eso es "no se sabe", no "fuera
  de línea".
- Cola de Windows: el spooler aceptar el trabajo no prueba nada. Se sigue el
  trabajo en la cola y, si no se confirma en papel o se cancela la prueba, se
  lo borra. Si no, la impresora lo imprime sola más tarde (cuando la prendan)
  y aparece un "ticket fantasma" en medio del servicio.
"""

import secrets
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common import printer_setup as ps

logger = getLogger("Asistente.Prueba")

# Sin letras ni números que se confundan al leerlos del papel (0/O, 1/I, 5/S...).
ALFABETO_CODIGO = "ACDEFHJKMNPRTUVWXY3479"
LARGO_CODIGO = 4

# Cuánto se espera una respuesta de estado, y cuánto se sigue un trabajo en la
# cola de Windows antes de decir que no salió.
ESPERA_ESTADO = 2.0
ESPERA_COLA_WINDOWS = 20.0
# Tope para mandar el ticket de prueba por un puerto COM. python-escpos abre el
# puerto con control de flujo DSR/DTR y sin límite de escritura: si la
# impresora (o el cable) no levanta DSR, la escritura esperaría para siempre.
ESPERA_ESCRITURA_SERIE = 10.0

# Problemas, con la acción concreta que se le muestra a la persona.
FUERA_DE_LINEA = "fuera_de_linea"
SIN_PAPEL = "sin_papel"
TAPA_ABIERTA = "tapa_abierta"
ERROR_IMPRESORA = "error_impresora"
NO_RESPONDE = "no_responde"
RECHAZADA = "rechazada"
TIMEOUT = "timeout"
ACCESO_DENEGADO = "acceso_denegado"
NO_ENCONTRADA = "no_encontrada"
EN_COLA = "en_cola"
ERROR = "error"

ACCIONES = {
    FUERA_DE_LINEA: "La impresora está fuera de línea. Revisá que esté encendida y "
                    "que no tenga ninguna luz de error prendida.",
    SIN_PAPEL: "La impresora no tiene papel. Cargá un rollo nuevo y probá otra vez.",
    TAPA_ABIERTA: "La tapa de la impresora está abierta. Cerrala bien hasta que "
                  "haga clic y probá otra vez.",
    ERROR_IMPRESORA: "La impresora informa un error (por ejemplo, el cortador "
                     "trabado). Apagala, esperá unos segundos, prendela y probá otra vez.",
    NO_RESPONDE: "La impresora no responde. Revisá que esté encendida y bien conectada.",
    RECHAZADA: "Hay un equipo en esa dirección, pero no acepta tickets. Puede que "
               "no sea la impresora.",
    TIMEOUT: "La impresora tardó demasiado en responder. Revisá que esté encendida "
             "y bien conectada.",
    ACCESO_DENEGADO: "Windows no dejó usar la impresora: puede que otro programa la "
                     "esté usando. Cerralo y probá otra vez.",
    NO_ENCONTRADA: "No se encontró la impresora. Revisá que esté encendida y que el "
                   "cable esté bien enchufado.",
    EN_COLA: "Windows recibió el ticket pero la impresora no lo imprimió. Revisá "
             "que esté encendida, con papel y con la tapa cerrada.",
    ERROR: "No se pudo imprimir la prueba.",
}
AVISO_PAPEL_POR_ACABARSE = "Al rollo le queda poco papel: tené uno a mano."

TIPOS_DE_CONEXION = {
    ps.WINDOWS: "Cola de Windows",
    ps.NETWORK: "Red",
    ps.USBPRINT: "USB",
    ps.SERIAL: "USB (puerto COM)",
    ps.USB: "USB",
}

# Estados de un trabajo en la cola de Windows (JOB_INFO_1.Status).
JOB_STATUS_ERROR = 0x00000002
JOB_STATUS_DELETING = 0x00000004
JOB_STATUS_OFFLINE = 0x00000020
JOB_STATUS_PAPEROUT = 0x00000040
JOB_STATUS_PRINTED = 0x00000080
JOB_STATUS_DELETED = 0x00000100
JOB_STATUS_BLOCKED_DEVQ = 0x00000200
JOB_STATUS_USER_INTERVENTION = 0x00000400
JOB_STATUS_COMPLETE = 0x00001000
JOB_CONTROL_DELETE = 5


def nuevo_codigo():
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))


# --------------------------------------------------------------------------
# Estado real de la impresora (DLE EOT)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class EstadoImpresora:
    """Lo que la impresora dice de sí misma. `responde` False = no se sabe."""

    responde: bool = False
    en_linea: bool = True
    tapa_abierta: bool = False
    sin_papel: bool = False
    papel_por_acabarse: bool = False
    error: bool = False

    @property
    def problema(self):
        if not self.responde:
            return None
        if self.tapa_abierta:
            return TAPA_ABIERTA
        if self.sin_papel:
            return SIN_PAPEL
        if self.error:
            return ERROR_IMPRESORA
        if not self.en_linea:
            return FUERA_DE_LINEA
        return None


def _consultar(driver, comando):
    """Un byte de respuesta a DLE EOT n, o None si la impresora no contesta."""
    try:
        driver._raw(comando)
        respuesta = driver._read()
    except (NotImplementedError, AttributeError):
        return None
    except (socket.timeout, TimeoutError):
        return None
    except OSError:
        return None
    except Exception as e:
        logger.debug(f"Consulta de estado sin respuesta: {e}")
        return None
    if not respuesta:
        return None
    return respuesta[0]


def _acortar_espera(driver, segundos):
    """
    La lectura de estado no puede heredar los 10 s del timeout de impresión:
    con una impresora que no contesta DLE EOT, serían 10 s por consulta.

    python-escpos abre la conexión recién al primer uso (`driver.device`): se
    la abre acá, y si no se puede abrir el error sube tal cual a probar().
    """
    dispositivo = driver.device
    if not dispositivo:
        return
    try:
        if hasattr(dispositivo, "settimeout"):      # Network (socket)
            dispositivo.settimeout(segundos)
        elif hasattr(dispositivo, "timeout"):       # Serial (pyserial) y UsbPrint
            dispositivo.timeout = segundos
        if hasattr(dispositivo, "write_timeout"):   # Serial y UsbPrint: escribir con tope
            dispositivo.write_timeout = ESPERA_ESCRITURA_SERIE
    except Exception:
        pass


def leer_estado(driver, espera=ESPERA_ESTADO):
    """
    Estado por DLE EOT 1 (en línea), 2 (tapa, papel, error) y 4 (sensor de
    papel). Si la impresora no contesta la primera consulta no se insiste.
    """
    _acortar_espera(driver, espera)
    general = _consultar(driver, b"\x10\x04\x01")
    if general is None:
        return EstadoImpresora(responde=False)
    causa = _consultar(driver, b"\x10\x04\x02") or 0
    papel = _consultar(driver, b"\x10\x04\x04") or 0
    return EstadoImpresora(
        responde=True,
        en_linea=not (general & 0x08),
        tapa_abierta=bool(causa & 0x04),
        sin_papel=bool(causa & 0x20) or (papel & 0x60) == 0x60,
        papel_por_acabarse=(papel & 0x0C) == 0x0C,
        error=bool(causa & 0x40),
    )


# --------------------------------------------------------------------------
# Trabajos en la cola de Windows
# --------------------------------------------------------------------------

class TrabajoWindows:
    """El trabajo de prueba en una cola de Windows, para seguirlo o borrarlo."""

    def __init__(self, printer_name, job_id, win32print=None):
        self.printer_name = printer_name
        self.job_id = job_id
        self._w32 = win32print

    def _api(self):
        if self._w32 is None:
            import win32print  # solo existe en Windows
            self._w32 = win32print
        return self._w32

    def estado(self):
        """Status del trabajo, o None si ya no está en la cola."""
        w32 = self._api()
        handle = w32.OpenPrinter(self.printer_name)
        try:
            info = w32.GetJob(handle, self.job_id, 1)
        except Exception:
            # Ya salió de la cola (o la cola no lo conoce): se mandó al equipo.
            return None
        finally:
            w32.ClosePrinter(handle)
        return int(info.get("Status") or 0)

    def esperar_resultado(self, espera=ESPERA_COLA_WINDOWS, pausa=0.5):
        """
        Sigue el trabajo hasta que sale de la cola o se traba.

        Returns:
            None si se mandó a la impresora, o la clave del problema.
        """
        limite = time.monotonic() + espera
        while True:
            try:
                estado = self.estado()
            except Exception as e:
                logger.warning(f"No se pudo seguir el trabajo de prueba: {e}")
                return None
            if estado is None or estado & (JOB_STATUS_PRINTED | JOB_STATUS_COMPLETE
                                           | JOB_STATUS_DELETED):
                return None
            if estado & JOB_STATUS_PAPEROUT:
                return SIN_PAPEL
            if estado & JOB_STATUS_OFFLINE:
                return FUERA_DE_LINEA
            if estado & (JOB_STATUS_ERROR | JOB_STATUS_BLOCKED_DEVQ
                         | JOB_STATUS_USER_INTERVENTION):
                return EN_COLA
            if time.monotonic() >= limite:
                return EN_COLA
            time.sleep(pausa)

    def cancelar(self):
        """Borra el trabajo si todavía está en la cola. True si lo borró."""
        try:
            if self.estado() is None:
                return False
            w32 = self._api()
            handle = w32.OpenPrinter(self.printer_name)
            try:
                w32.SetJob(handle, self.job_id, 0, None, JOB_CONTROL_DELETE)
            finally:
                w32.ClosePrinter(handle)
            logger.info("Trabajo de prueba %s borrado de la cola %s.",
                        self.job_id, self.printer_name)
            return True
        except Exception as e:
            logger.warning(f"No se pudo borrar el trabajo de prueba: {e}")
            return False


# --------------------------------------------------------------------------
# La prueba
# --------------------------------------------------------------------------

@dataclass
class ResultadoPrueba:
    exito_tecnico: bool
    codigo: str
    problema: str = None
    detalle: str = ""
    estado_antes: EstadoImpresora = None
    estado_despues: EstadoImpresora = None
    trabajo: TrabajoWindows = None
    avisos: list = field(default_factory=list)
    # USB directo: estado LPT de usbprint, solo como dato para soporte. Muchas
    # térmicas devuelven siempre lo mismo: no decide nada (lo decide DLE EOT).
    lpt: dict = field(default_factory=dict)
    # Cola de Windows: si el trabajo de prueba se borró (para soporte, #185).
    trabajo_borrado: bool = False

    @property
    def accion(self):
        """Qué tiene que hacer la persona, en sus palabras."""
        return ACCIONES.get(self.problema, "") if self.problema else ""

    def descartar(self):
        """
        La prueba no se confirmó en papel, o se canceló: que no quede nada
        pendiente que la impresora imprima sola más tarde.
        """
        if self.trabajo is not None:
            borrado = self.trabajo.cancelar()
            self.trabajo_borrado = self.trabajo_borrado or bool(borrado)
            return borrado
        return False


def contenido_del_ticket(candidato, alias, comercio, codigo, ahora):
    """Las líneas del ticket, para imprimir y para los tests."""
    tipo = TIPOS_DE_CONEXION.get(candidato.connection, candidato.connection)
    if candidato.detail:
        tipo = f"{tipo} ({candidato.detail})"
    return {
        "titulo": "PRUEBA DE IMPRESORA",
        "lineas": [
            f"Comercio: {comercio or '-'}",
            f"Impresora: {alias or candidato.display_name}",
            f"Conexión: {tipo}",
            f"Fecha: {ahora:%d/%m/%Y %H:%M}",
        ],
        "codigo": codigo,
        "pie": "Si podés leer este ticket, la impresora funciona. "
               "Confirmalo en la pantalla de Fiscalberry.",
    }


def _imprimir(driver, contenido):
    driver.set(align="center", bold=True, double_height=True, double_width=True)
    driver.textln(contenido["titulo"])
    driver.set(align="left", bold=False, normal_textsize=True)
    driver.textln("-" * 32)
    for linea in contenido["lineas"]:
        driver.textln(linea)
    driver.textln("-" * 32)
    driver.set(align="center", bold=False, normal_textsize=True)
    driver.textln("Código")
    driver.set(align="center", bold=True, double_height=True, double_width=True)
    driver.textln(contenido["codigo"])
    driver.set(align="center", bold=False, normal_textsize=True)
    driver.textln("")
    driver.textln(contenido["pie"])
    driver.cut()


# Códigos de error. errno y winerror se miran por separado: el 5 es "acceso
# denegado" en Windows pero EIO en Linux.
_POR_ERRNO = {
    RECHAZADA: {111, 10061},                  # ECONNREFUSED (Windows usa el código WSA)
    TIMEOUT: {110, 10060},                    # ETIMEDOUT
    NO_RESPONDE: {101, 113, 10051, 10065},    # red / host inalcanzable
    ACCESO_DENEGADO: {13},                    # EACCES
    NO_ENCONTRADA: {2},                       # ENOENT (ej. el COM ya no existe)
}
_POR_WINERROR = {
    RECHAZADA: {10061},
    TIMEOUT: {10060, 121, 1460},              # WSAETIMEDOUT, ERROR_SEM_TIMEOUT, ERROR_TIMEOUT
    NO_RESPONDE: {10051, 10065},
    # ERROR_ACCESS_DENIED; UsbPrint: ERROR_SHARING_VIOLATION y ERROR_BUSY (el
    # spooler la está usando y no la soltó después de los reintentos).
    ACCESO_DENEGADO: {5, 32, 170},
    # No existe, nombre de impresora inválido; UsbPrint: desenchufada
    # (ERROR_DEVICE_NOT_CONNECTED, ERROR_NO_SUCH_DEVICE, ERROR_GEN_FAILURE).
    NO_ENCONTRADA: {2, 3, 1801, 1167, 433, 31},
}

# Por si no hay código: los textos vienen en el idioma de Windows.
_POR_TEXTO = (
    (RECHAZADA, ("refused", "denegó", "rechaz")),
    (TIMEOUT, ("timed out", "write timeout", "no respondió", "tiempo de espera")),
    (NO_RESPONDE, ("no route", "unreachable", "inaccesible", "no accesible")),
    (ACCESO_DENEGADO, ("access is denied", "acceso denegado", "permissionerror")),
    (NO_ENCONTRADA, ("not found", "incorrect printer name", "no se encontr",
                     "filenotfounderror", "no existe", "unable to start a print job")),
)


def _cadena(error):
    """El error y los que lo causaron (python-escpos los envuelve)."""
    vistos = []
    while error is not None and error not in vistos and len(vistos) < 10:
        vistos.append(error)
        error = error.__cause__ or error.__context__
    return vistos


def clasificar_error(error):
    """Una excepción del driver, a un problema con acción para la persona."""
    cadena = _cadena(error)
    for e in cadena:
        if isinstance(e, ConnectionRefusedError):
            return RECHAZADA
        if isinstance(e, (socket.timeout, TimeoutError)):
            return TIMEOUT
        if isinstance(e, PermissionError):
            return ACCESO_DENEGADO
        winerror = getattr(e, "winerror", None)
        args = getattr(e, "args", ())
        if (winerror is None and not isinstance(e, OSError)
                and args and isinstance(args[0], int)):
            winerror = args[0]          # pywintypes.error(5, 'OpenPrinter', ...)
        errno = getattr(e, "errno", None) if isinstance(e, OSError) else None
        for problema, conocidos in _POR_WINERROR.items():
            if winerror in conocidos:
                return problema
        for problema, conocidos in _POR_ERRNO.items():
            if errno in conocidos:
                return problema

    texto = " ".join(str(e) for e in cadena).casefold()
    for problema, palabras in _POR_TEXTO:
        if any(p in texto for p in palabras):
            return problema
    return ERROR


def probar(candidato, alias, comercio="", codigo=None, ahora=None,
           crear_driver=None, win32print=None, espera_cola=ESPERA_COLA_WINDOWS,
           espera_estado=ESPERA_ESTADO):
    """
    Imprime el ticket de prueba de un candidato todavía sin guardar.

    No escribe config.ini ni publica errores al backend. Corre en el hilo que
    lo llame: la interfaz lo tiene que llamar fuera del hilo de Kivy.
    """
    if crear_driver is None:
        from fiscalberry.common.ComandosHandler import build_driver as crear_driver

    codigo = codigo or nuevo_codigo()
    ahora = ahora or datetime.now()
    contenido = contenido_del_ticket(candidato, alias, comercio, codigo, ahora)
    resultado = ResultadoPrueba(exito_tecnico=False, codigo=codigo)

    try:
        driver = crear_driver(candidato.driver_config)[0]
    except Exception as e:
        resultado.problema = clasificar_error(e)
        resultado.detalle = str(e)
        return resultado

    trabajo = None
    try:
        if candidato.status_readable:
            resultado.estado_antes = leer_estado(driver, espera_estado)
            if resultado.estado_antes.problema:
                resultado.problema = resultado.estado_antes.problema
                return resultado

        _imprimir(driver, contenido)

        if candidato.connection == ps.WINDOWS:
            job_id = getattr(driver, "current_job", None)
            if job_id:
                trabajo = TrabajoWindows(candidato.driver_config["printer_name"],
                                         job_id, win32print)

        if hasattr(driver, "lpt_status"):
            resultado.lpt = driver.lpt_status()

        if candidato.status_readable:
            resultado.estado_despues = leer_estado(driver, espera_estado)
            if resultado.estado_despues.problema:
                resultado.problema = resultado.estado_despues.problema
                return resultado
            if resultado.estado_despues.papel_por_acabarse:
                resultado.avisos.append(AVISO_PAPEL_POR_ACABARSE)
    except Exception as e:
        resultado.problema = clasificar_error(e)
        resultado.detalle = str(e)
        return resultado
    finally:
        try:
            driver.close()
        except Exception:
            pass

    # Cola de Windows: recién al cerrar el documento el trabajo queda completo
    # en la cola. Que el spooler lo haya aceptado no prueba nada: se lo sigue.
    if trabajo is not None:
        resultado.trabajo = trabajo
        problema = trabajo.esperar_resultado(espera=espera_cola)
        if problema:
            resultado.problema = problema
            # Trabado en la cola: se borra ya, para que no salga solo después.
            resultado.trabajo_borrado = bool(trabajo.cancelar())
            return resultado

    resultado.exito_tecnico = True
    return resultado


def finalizar(service, alias, candidato, resultado, salio_en_papel):
    """
    Cierra la prueba con la respuesta de la persona.

    - "No salió": se descarta lo pendiente (el trabajo en la cola de Windows)
      y no se guarda nada.
    - "Salió": se guarda, solo si la prueba técnica también salió bien.

    Returns:
        El nombre con que quedó guardada, o None.
    """
    if not salio_en_papel or not resultado.exito_tecnico:
        resultado.descartar()
        return None
    return service.save_confirmed(alias, candidato, technical_success=True,
                                  physical_confirmed=True)
