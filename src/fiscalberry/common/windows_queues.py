"""
Colas de impresión de Windows que ya existen (escenario 4 del asistente, #174).

Fiscalberry no crea colas ni instala drivers: si la impresora ya tiene una cola
en Windows, el asistente la ofrece directamente y se imprime por Win32Raw.

Dos decisiones de diseño:

- La enumeración corre en un SUBPROCESO que se puede matar. EnumPrinters con
  PRINTER_ENUM_CONNECTIONS consulta las colas compartidas de otras PCs, y una
  compartida de una PC apagada (\\\\caja\\cocina) puede colgar la llamada más de
  30 segundos. Un hilo de Python no se puede cancelar; un proceso sí. El
  proceso es el mismo ejecutable en modo `--list-printers`, y como la GUI de
  Windows no tiene consola, deja el resultado en un archivo (`--report`).
- Lo que dice el spooler es solo informativo: muchos puertos TCP/IP y drivers
  POS dicen "Lista" aunque la impresora esté apagada. La verdad la da el
  ticket de prueba (#172).
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field

from fiscalberry.common.printer_setup import PrinterCandidate

# EnumPrinters
PRINTER_ENUM_LOCAL = 0x00000002
PRINTER_ENUM_CONNECTIONS = 0x00000004

# PRINTER_INFO_2.Attributes
PRINTER_ATTRIBUTE_NETWORK = 0x00000010
PRINTER_ATTRIBUTE_LOCAL = 0x00000040
PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x00000400
PRINTER_ATTRIBUTE_FAX = 0x00004000

# PRINTER_INFO_2.Status (los que importan para decidir)
PRINTER_STATUS_PAUSED = 0x00000001
PRINTER_STATUS_ERROR = 0x00000002
PRINTER_STATUS_PAPER_JAM = 0x00000008
PRINTER_STATUS_PAPER_OUT = 0x00000010
PRINTER_STATUS_OFFLINE = 0x00000080
PRINTER_STATUS_NOT_AVAILABLE = 0x00001000
PRINTER_STATUS_DOOR_OPEN = 0x00400000
PRINTER_STATUS_SERVER_UNKNOWN = 0x00800000
PRINTER_STATUS_SERVER_OFFLINE = 0x02000000

_ESTADOS_FUERA_DE_LINEA = (PRINTER_STATUS_OFFLINE | PRINTER_STATUS_NOT_AVAILABLE
                           | PRINTER_STATUS_SERVER_UNKNOWN | PRINTER_STATUS_SERVER_OFFLINE)

# Colas que no son impresoras: generan archivos, mandan faxes o van a OneNote.
_PUERTOS_VIRTUALES = ("portprompt:", "file:", "xpsport:", "shrfax:", "nul:")
_PALABRAS_VIRTUALES = (
    "pdf", "xps", "onenote", "fax", "document writer", "snagit",
    "microsoft software printer driver",
)

# Una búsqueda normal termina en menos de 5 s. Esto es para el caso colgado.
LISTADO_TIMEOUT = 10.0

# Errores de listar_colas().
ERROR_TIMEOUT = "timeout"
ERROR_CANCELADO = "cancelado"
ERROR_SPOOLER = "spooler"
ERROR_NO_WINDOWS = "no_windows"

EXPLICACIONES = {
    ERROR_TIMEOUT: (
        "Windows tardó demasiado en mostrar sus impresoras. Suele pasar cuando "
        "hay una impresora compartida de otra computadora que está apagada. "
        "Probá de nuevo; la impresora también se puede buscar por red o USB."
    ),
    ERROR_SPOOLER: (
        "Windows no pudo mostrar sus impresoras: el servicio de impresión "
        "(Cola de impresión) puede estar detenido. Reiniciar la computadora "
        "suele resolverlo."
    ),
    ERROR_NO_WINDOWS: "Las colas de impresión solo existen en Windows.",
    ERROR_CANCELADO: "",
}

_CREATE_NO_WINDOW = 0x08000000


# --------------------------------------------------------------------------
# Clasificación (pura: se prueba con fixtures)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ColaWindows:
    nombre: str
    driver: str = ""
    puerto: str = ""
    servidor: str = ""
    atributos: int = 0
    estado: int = 0
    local: bool = True
    compartida: bool = False
    virtual: bool = False
    fuera_de_linea: bool = False

    @property
    def lista(self):
        """El spooler no reporta problemas (informativo: ver docstring)."""
        return not self.fuera_de_linea and not (
            self.estado & (PRINTER_STATUS_PAUSED | PRINTER_STATUS_ERROR
                           | PRINTER_STATUS_PAPER_JAM | PRINTER_STATUS_PAPER_OUT
                           | PRINTER_STATUS_DOOR_OPEN))

    def candidato(self):
        return PrinterCandidate.windows_queue(self.nombre, self.puerto)


def clasificar(cruda):
    """Una entrada de PRINTER_INFO_2 (como la deja el subproceso) a ColaWindows."""
    nombre = str(cruda.get("nombre") or "").strip()
    driver = str(cruda.get("driver") or "").strip()
    puerto = str(cruda.get("puerto") or "").strip()
    servidor = str(cruda.get("servidor") or "").strip()
    atributos = int(cruda.get("atributos") or 0)
    estado = int(cruda.get("estado") or 0)

    compartida = (nombre.startswith("\\\\") or bool(servidor)
                  or bool(atributos & PRINTER_ATTRIBUTE_NETWORK))
    texto = f"{nombre} {driver} {puerto}".casefold()
    virtual = (bool(atributos & PRINTER_ATTRIBUTE_FAX)
               or puerto.casefold().startswith(_PUERTOS_VIRTUALES)
               or puerto.casefold().startswith("microsoft.office.onenote")
               or any(p in texto for p in _PALABRAS_VIRTUALES))
    fuera_de_linea = (bool(atributos & PRINTER_ATTRIBUTE_WORK_OFFLINE)
                      or bool(estado & _ESTADOS_FUERA_DE_LINEA))

    return ColaWindows(
        nombre=nombre, driver=driver, puerto=puerto, servidor=servidor,
        atributos=atributos, estado=estado, local=not compartida,
        compartida=compartida, virtual=virtual, fuera_de_linea=fuera_de_linea,
    )


def ordenar(colas, mostrar_todas=False):
    """
    Las colas para mostrar, en el orden en que conviene ofrecerlas.

    - Primero las locales listas: es casi seguro que la impresora está ahí.
    - Se ocultan las virtuales (PDF, XPS, OneNote, fax) y las fuera de línea,
      salvo que se pidan todas.
    - Una cola que Windows lista dos veces (local y como conexión) aparece una
      sola vez.
    """
    unicas = {}
    for cola in colas:
        if not cola.nombre:
            continue
        clave = cola.nombre.casefold()
        previa = unicas.get(clave)
        # Si aparece dos veces, se queda con la más útil; a igual utilidad, la
        # elección no puede depender del orden en que la devolvió Windows.
        if previa is None or _orden(cola) < _orden(previa):
            unicas[clave] = cola

    visibles = [c for c in unicas.values()
                if mostrar_todas or not (c.virtual or c.fuera_de_linea)]
    return sorted(visibles, key=_orden)


def _prioridad(cola):
    return (cola.virtual, cola.fuera_de_linea, cola.compartida, not cola.lista)


def _orden(cola):
    return (_prioridad(cola), cola.nombre.casefold(), cola.nombre, cola.puerto)


# --------------------------------------------------------------------------
# El subproceso
# --------------------------------------------------------------------------

def enumerar_crudas(win32print=None):
    """Lo que corre DENTRO del subproceso: EnumPrinters nivel 2."""
    if win32print is None:
        import win32print  # noqa: F811  (solo existe en Windows)

    flags = PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    crudas = []
    for info in win32print.EnumPrinters(flags, None, 2):
        # Solo campos simples: pDevMode y pSecurityDescriptor no son JSON.
        crudas.append({
            "nombre": info.get("pPrinterName") or "",
            "driver": info.get("pDriverName") or "",
            "puerto": info.get("pPortName") or "",
            "servidor": info.get("pServerName") or "",
            "atributos": int(info.get("Attributes") or 0),
            "estado": int(info.get("Status") or 0),
        })
    return crudas


def run_list_printers(ruta_reporte=None, win32print=None):
    """Modo `--list-printers`. Devuelve el código de salida del proceso."""
    try:
        datos = {"ok": True, "colas": enumerar_crudas(win32print)}
        codigo = 0
    except ImportError:
        datos = {"ok": False, "error": ERROR_NO_WINDOWS}
        codigo = 2
    except Exception as e:
        datos = {"ok": False, "error": ERROR_SPOOLER, "detalle": str(e)}
        codigo = 1

    texto = json.dumps(datos, ensure_ascii=False)
    if not ruta_reporte:
        print(texto)
        return codigo
    tmp = ruta_reporte + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(texto)
    os.replace(tmp, ruta_reporte)
    return codigo


def comando_listado(reporte):
    """El mismo ejecutable en modo listado (o el módulo, corriendo desde código)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--list-printers", "--report", reporte]
    return [sys.executable, "-m", "fiscalberry.common.windows_queues", "--report", reporte]


@dataclass
class ResultadoListado:
    colas: list = field(default_factory=list)
    error: str = None
    detalle: str = ""

    @property
    def explicacion(self):
        return EXPLICACIONES.get(self.error, "") if self.error else ""


def _matar(proceso):
    try:
        proceso.kill()
    except OSError:
        pass
    try:
        proceso.wait(timeout=5)
    except Exception:
        pass


def listar_colas(timeout=LISTADO_TIMEOUT, cancelar=None, popen=subprocess.Popen,
                 comando=comando_listado):
    """
    Las colas de Windows, clasificadas y sin ordenar (ver `ordenar`).

    Nunca tarda más que `timeout`, y `cancelar` (un threading.Event) corta la
    búsqueda al instante: en los dos casos el subproceso se termina.
    """
    with tempfile.TemporaryDirectory(prefix="fiscalberry-colas-") as carpeta:
        reporte = os.path.join(carpeta, "colas.json")
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                  "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        try:
            proceso = popen(comando(reporte), **kwargs)
        except OSError as e:
            return ResultadoListado(error=ERROR_SPOOLER, detalle=str(e))

        limite = time.monotonic() + timeout
        while proceso.poll() is None:
            if cancelar is not None and cancelar.is_set():
                _matar(proceso)
                return ResultadoListado(error=ERROR_CANCELADO)
            if time.monotonic() >= limite:
                _matar(proceso)
                return ResultadoListado(
                    error=ERROR_TIMEOUT,
                    detalle=f"el listado no terminó en {timeout:.0f} s")
            time.sleep(0.05)

        try:
            with open(reporte, "r", encoding="utf-8") as fh:
                datos = json.load(fh)
        except (OSError, ValueError) as e:
            return ResultadoListado(
                error=ERROR_SPOOLER,
                detalle=f"el listado terminó con código {proceso.returncode} sin "
                        f"dejar resultado ({e})")

    if not datos.get("ok"):
        return ResultadoListado(error=datos.get("error") or ERROR_SPOOLER,
                                detalle=datos.get("detalle", ""))
    return ResultadoListado(colas=[clasificar(c) for c in datos.get("colas", [])])


class BusquedaDeColas:
    """
    Buscar colas sin bloquear la interfaz, con la posibilidad de cancelar.

    `al_terminar(resultado)` corre en el hilo de la búsqueda: la interfaz lo
    tiene que llevar a su propio hilo (en Kivy, con @mainthread).
    """

    def __init__(self, al_terminar, timeout=LISTADO_TIMEOUT, listar=listar_colas):
        self._al_terminar = al_terminar
        self._timeout = timeout
        self._listar = listar
        self._cancelar = threading.Event()
        self._hilo = None

    def iniciar(self):
        self._cancelar.clear()
        self._hilo = threading.Thread(target=self._correr, daemon=True,
                                      name="fiscalberry-colas")
        self._hilo.start()
        return self

    def _correr(self):
        try:
            resultado = self._listar(timeout=self._timeout, cancelar=self._cancelar)
        except Exception as e:
            resultado = ResultadoListado(error=ERROR_SPOOLER, detalle=str(e))
        if resultado.error == ERROR_CANCELADO:
            return
        self._al_terminar(resultado)

    def cancelar(self):
        self._cancelar.set()

    def esperar(self, timeout=None):
        if self._hilo is not None:
            self._hilo.join(timeout)


if __name__ == "__main__":
    def _arg(nombre):
        if nombre in sys.argv:
            i = sys.argv.index(nombre)
            if i + 1 < len(sys.argv):
                return sys.argv[i + 1]
        return None

    sys.exit(run_list_printers(ruta_reporte=_arg("--report")))
