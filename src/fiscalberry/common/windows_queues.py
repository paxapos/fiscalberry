"""
Colas de impresión de Windows que ya existen (#174, escenario 4).

Fiscalberry no crea colas ni instala drivers: solo ofrece las que hay, para
imprimir por ellas con Win32Raw (bytes crudos al spooler).

- Se enumeran con EnumPrinters(PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS,
  nivel 2): nombre, puerto, driver, atributos y estado.
- **En un subproceso que se puede matar** (`fiscalberry-gui.exe
  --list-printers`): una cola compartida caída (\\\\servidor\\cola) puede colgar
  EnumPrinters más de 30 s, y un hilo de Python no se puede cancelar. Si el
  subproceso no termina a tiempo se lo mata y se reintenta solo con las
  colas locales (las compartidas son las que cuelgan).
- Se ocultan por defecto PDF, XPS, OneNote, fax y colas fuera de línea; la
  pantalla las muestra con "Mostrar todas".
- El estado del spooler es solo informativo: muchos puertos TCP/IP y drivers
  POS dicen "Lista" con la impresora apagada. La verdad la da la prueba en
  papel (#172).
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("WindowsQueues")

PRINTER_ENUM_LOCAL = 0x2
PRINTER_ENUM_CONNECTIONS = 0x4

PRINTER_ATTRIBUTE_DEFAULT = 0x4
PRINTER_ATTRIBUTE_SHARED = 0x8
PRINTER_ATTRIBUTE_NETWORK = 0x10
PRINTER_ATTRIBUTE_LOCAL = 0x40
PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x400
PRINTER_ATTRIBUTE_FAX = 0x4000

PRINTER_STATUS_PAUSED = 0x1
PRINTER_STATUS_ERROR = 0x2
PRINTER_STATUS_PAPER_JAM = 0x8
PRINTER_STATUS_PAPER_OUT = 0x10
PRINTER_STATUS_OFFLINE = 0x80
PRINTER_STATUS_NOT_AVAILABLE = 0x1000
PRINTER_STATUS_DOOR_OPEN = 0x400000
PRINTER_STATUS_USER_INTERVENTION = 0x100000
PRINTER_STATUS_SERVER_UNKNOWN = 0x800000

# Detección normal: < 5 s (#174). Con margen para el arranque del exe.
LIST_TIMEOUT = 8.0
LOCAL_ONLY_TIMEOUT = 5.0

_VIRTUAL_WORDS = (
    "pdf", "xps", "onenote", "fax", "document writer", "send to", "enviar a",
    "microsoft print to", "imprimir en", "snagit", "cutepdf", "pdfcreator",
    "bullzip", "dopdf", "foxit", "nitro", "adobe", "image writer",
)
_VIRTUAL_PORTS = ("portprompt:", "nul:", "file:", "shrfax:", "xpsport:", "pdf", "onenote")

KIND_USB = "usb"
KIND_SERIAL = "serie"
KIND_PARALLEL = "paralelo"
KIND_NETWORK = "red"
KIND_SHARED = "compartida"
KIND_VIRTUAL = "virtual"
KIND_OTHER = "otro"


@dataclass(frozen=True)
class WindowsQueue:
    name: str
    port: str = ""
    driver: str = ""
    attributes: int = 0
    status: int = 0
    server: str = ""
    share_name: str = ""
    location: str = ""
    comment: str = ""
    is_default: bool = False

    # -- clasificación ------------------------------------------------------

    @property
    def ports(self):
        return [p.strip() for p in self.port.split(",") if p.strip()]

    @property
    def shared_connection(self):
        """Conectada a una cola de otra PC (\\\\servidor\\cola)."""
        return bool(self.server) or self.name.startswith("\\\\") \
            or bool(self.attributes & PRINTER_ATTRIBUTE_NETWORK)

    @property
    def virtual(self):
        texto = f"{self.name} {self.driver}".lower()
        if self.attributes & PRINTER_ATTRIBUTE_FAX:
            return True
        if any(p in texto for p in _VIRTUAL_WORDS):
            return True
        puertos = " ".join(self.ports).lower()
        return any(p in puertos for p in _VIRTUAL_PORTS)

    @property
    def offline(self):
        return bool(self.attributes & PRINTER_ATTRIBUTE_WORK_OFFLINE) or bool(
            self.status & (PRINTER_STATUS_OFFLINE | PRINTER_STATUS_NOT_AVAILABLE
                           | PRINTER_STATUS_SERVER_UNKNOWN))

    @property
    def ready(self):
        return not self.offline and self.status == 0

    @property
    def hidden(self):
        """Oculta por defecto: virtual, de fax o fuera de línea."""
        return self.virtual or self.offline

    @property
    def kind(self):
        if self.virtual:
            return KIND_VIRTUAL
        if self.shared_connection:
            return KIND_SHARED
        puerto = (self.ports[0] if self.ports else "").upper()
        if re.match(r"^USB\d+$", puerto):
            return KIND_USB
        if re.match(r"^COM\d+:?$", puerto):
            return KIND_SERIAL
        if re.match(r"^LPT\d+:?$", puerto):
            return KIND_PARALLEL
        if puerto.startswith(("IP_", "WSD-", "TCPMON", "HTTP")) or \
                re.match(r"^\d+\.\d+\.\d+\.\d+(_\d+)?$", puerto):
            return KIND_NETWORK
        return KIND_OTHER

    @property
    def usb_ports(self):
        return {p.upper() for p in self.ports if re.match(r"^USB\d+$", p, re.I)}

    @property
    def com_ports(self):
        return {p.upper().rstrip(":") for p in self.ports if re.match(r"^COM\d+:?$", p, re.I)}

    @property
    def rank(self):
        """Primero las locales listas, después las locales, al final las compartidas."""
        if self.hidden:
            return 3
        if self.shared_connection:
            return 2
        return 0 if self.ready else 1

    @property
    def status_text(self):
        """Lo que dice Windows. Informativo: no prueba nada."""
        if self.attributes & PRINTER_ATTRIBUTE_WORK_OFFLINE or self.status & PRINTER_STATUS_OFFLINE:
            return "Windows la marca fuera de línea"
        if self.status & (PRINTER_STATUS_NOT_AVAILABLE | PRINTER_STATUS_SERVER_UNKNOWN):
            return "Windows no la encuentra"
        if self.status & PRINTER_STATUS_PAPER_OUT:
            return "Windows dice que no tiene papel"
        if self.status & PRINTER_STATUS_PAUSED:
            return "La cola está en pausa"
        if self.status & (PRINTER_STATUS_ERROR | PRINTER_STATUS_PAPER_JAM | PRINTER_STATUS_DOOR_OPEN
                          | PRINTER_STATUS_USER_INTERVENTION):
            return "Windows informa un error"
        return "Windows la muestra lista"

    def candidate(self):
        from fiscalberry.common.printer_setup import PrinterCandidate
        return PrinterCandidate.windows_queue(self.name, self.port)

    @classmethod
    def from_win32(cls, info, default_name=""):
        nombre = str(info.get("pPrinterName") or "").strip()
        return cls(
            name=nombre,
            port=str(info.get("pPortName") or "").strip(),
            driver=str(info.get("pDriverName") or "").strip(),
            attributes=int(info.get("Attributes") or 0),
            status=int(info.get("Status") or 0),
            server=str(info.get("pServerName") or "").strip(),
            share_name=str(info.get("pShareName") or "").strip(),
            location=str(info.get("pLocation") or "").strip(),
            comment=str(info.get("pComment") or "").strip(),
            is_default=bool(default_name) and nombre.casefold() == default_name.casefold(),
        )


def normalize(infos, default_name=""):
    """Colas únicas (Windows no distingue mayúsculas), en orden estable."""
    vistas = {}
    for info in infos:
        cola = WindowsQueue.from_win32(info, default_name)
        if not cola.name:
            continue
        clave = cola.name.casefold()
        # Si aparece dos veces (local y como conexión), queda la local; entre
        # iguales, siempre la misma, sin importar el orden en que llegaron.
        actual = vistas.get(clave)
        if actual is None or (cola.shared_connection, cola.name) < (actual.shared_connection,
                                                                   actual.name):
            vistas[clave] = cola
    return sorted(vistas.values(), key=lambda c: (c.rank, not c.is_default, c.name.casefold()))


def enumerate_in_process(win32print=None, local_only=False):
    """EnumPrinters nivel 2 en este proceso. Puede colgar: usar el subproceso."""
    if win32print is None:
        import win32print
    flags = PRINTER_ENUM_LOCAL if local_only else PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    infos = win32print.EnumPrinters(flags, None, 2) or []
    try:
        default = win32print.GetDefaultPrinter() or ""
    except Exception:
        default = ""
    return normalize(infos, default)


# -- El subproceso ---------------------------------------------------------------

def run_list_printers(ruta_reporte=None, local_only=False, win32print=None):
    """
    Modo `--list-printers`: escribe {"colas": [...], "error": ...} en JSON.
    Lo corre el exe como subproceso; el padre lo mata si se cuelga.
    """
    try:
        colas = [asdict(c) for c in enumerate_in_process(win32print, local_only)]
        datos = {"colas": colas, "error": None}
        codigo = 0
    except Exception as e:
        datos = {"colas": [], "error": f"{type(e).__name__}: {e}"}
        codigo = 1
    texto = json.dumps(datos, ensure_ascii=False)
    if ruta_reporte:
        with open(ruta_reporte, "w", encoding="utf-8") as fh:
            fh.write(texto)
    else:
        print(texto)
    return codigo


def list_printers_command(report_path, local_only=False, frozen=None, executable=None):
    """Cómo relanzarse para listar colas: el propio exe, o python -m en desarrollo."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    extra = ["--local-only"] if local_only else []
    if frozen:
        return [executable, "--list-printers", "--report", report_path] + extra
    return [executable, "-m", "fiscalberry.common.windows_queues", "--list-printers",
            "--report", report_path] + extra


@dataclass
class QueueListResult:
    queues: list = field(default_factory=list)
    error: str = ""
    timed_out: bool = False
    local_only: bool = False     # el resultado es del reintento sin las compartidas
    seconds: float = 0.0
    cancelled: bool = False
    skipped: bool = False        # no es Windows

    @property
    def message(self):
        """Explicación para la pantalla (vacía si todo salió bien)."""
        if self.timed_out and self.local_only and not self.error:
            return ("Una impresora compartida de otra computadora no respondió: "
                    "se muestran solo las de esta computadora.")
        if self.timed_out:
            return ("Windows tardó demasiado en listar las impresoras instaladas. "
                    "Probá de nuevo; si sigue igual, reiniciá la computadora.")
        if self.error:
            return "No se pudieron leer las impresoras instaladas en Windows."
        return ""


def _correr(comando, timeout, cancel, popen, clock):
    """(terminó, cancelado). Mata el proceso si vence o se cancela."""
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    env = dict(os.environ, KIVY_NO_ARGS="1", KIVY_NO_CONSOLELOG="1")
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env["PYTHONPATH"] = raiz + os.pathsep + env.get("PYTHONPATH", "")
    proceso = popen(comando, env=env, **kwargs)
    limite = clock() + timeout
    try:
        while True:
            try:
                proceso.wait(timeout=0.1)
                return True, False
            except subprocess.TimeoutExpired:
                pass
            if cancel is not None and cancel.is_set():
                return False, True
            if clock() >= limite:
                return False, False
    finally:
        if proceso.poll() is None:
            proceso.kill()
            try:
                proceso.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("El subproceso de colas no terminó ni al matarlo")


def _leer(ruta):
    try:
        with open(ruta, encoding="utf-8") as fh:
            datos = json.load(fh)
    except (OSError, ValueError) as e:
        return None, f"sin respuesta del subproceso: {e}"
    campos = set(WindowsQueue.__dataclass_fields__)
    colas = [WindowsQueue(**{k: v for k, v in c.items() if k in campos})
             for c in datos.get("colas", []) if isinstance(c, dict) and c.get("name")]
    return colas, datos.get("error") or ""


def list_queues(timeout=LIST_TIMEOUT, local_timeout=LOCAL_ONLY_TIMEOUT, cancel=None,
                platform=None, command=list_printers_command, popen=subprocess.Popen,
                clock=time.monotonic):
    """
    Colas de Windows sin arriesgar un cuelgue: subproceso con timeout, y si
    se cuelga, un segundo intento solo con las locales. No lanza.
    """
    platform = sys.platform if platform is None else platform
    inicio = clock()
    resultado = QueueListResult()
    if platform != "win32":
        resultado.skipped = True
        return resultado

    carpeta = tempfile.mkdtemp(prefix="fiscalberry-colas-")
    try:
        for solo_locales, espera in ((False, timeout), (True, local_timeout)):
            ruta = os.path.join(carpeta, f"colas-{int(solo_locales)}.json")
            try:
                termino, cancelado = _correr(command(ruta, solo_locales), espera, cancel, popen, clock)
            except OSError as e:
                logger.error(f"No se pudo lanzar el listado de colas: {e}")
                resultado.error = str(e)
                break
            if cancelado:
                resultado.cancelled = True
                break
            if not termino:
                logger.warning("El listado de colas de Windows no terminó en %.0f s%s",
                               espera, " (solo locales)" if solo_locales else "")
                resultado.timed_out = True
                continue
            colas, error = _leer(ruta)
            resultado.queues = colas or []
            resultado.error = error
            resultado.local_only = solo_locales
            break
    finally:
        for nombre in os.listdir(carpeta):
            try:
                os.remove(os.path.join(carpeta, nombre))
            except OSError:
                pass
        try:
            os.rmdir(carpeta)
        except OSError:
            pass
    resultado.seconds = clock() - inicio
    logger.info("Colas de Windows: %d en %.1f s%s", len(resultado.queues), resultado.seconds,
                " (solo locales)" if resultado.local_only else "")
    return resultado


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    ruta = None
    if "--report" in argv:
        i = argv.index("--report")
        ruta = argv[i + 1] if i + 1 < len(argv) else None
    return run_list_printers(ruta, local_only="--local-only" in argv)


if __name__ == "__main__":
    sys.exit(main())
