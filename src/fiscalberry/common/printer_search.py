"""
"Buscar impresoras" (#184): red (#175), USB/COM (#183) y colas de Windows
(#174) en paralelo, en un solo listado.

La persona no elige el tipo de conexión: ve una lista de impresoras con un
nombre y una frase sin jerga ("Conectada a la red", "Conectada por USB",
"Instalada en Windows"). IP, puerto, driver y demás quedan en `details`, que
la pantalla muestra solo en "Detalles".

Sin Kivy: `PrinterSearch.run` bloquea y se llama desde un hilo. Cada fuente
que termina avisa por `on_partial`, así la lista aparece de a poco (la red y
el USB tardan ~2 s; las colas pueden tardar más si hay una compartida caída).

Una misma impresora puede aparecer por dos caminos. Reglas:

- Cola de Windows sobre USB001 + impresora usbprint en USB001: queda la cola
  (es lo que el local ya usa y el spooler no se pelea con nadie).
- Cola sobre COM3 + puerto COM3: queda la cola, por lo mismo.
- Cola con puerto TCP/IP a 192.168.1.50 + impresora de red 192.168.1.50:
  queda la de red, directo por TCP 9100 (lee el estado real).

Lo que se oculta así no desaparece: se ve con "Mostrar todas".
"""

import ipaddress
import re
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Optional

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.printer_guides import GUIDE_USB_DRIVER

logger = getLogger("PrinterSearch")

SOURCE_NETWORK = "red"
SOURCE_USB = "usb"
SOURCE_SERIAL = "com"
SOURCE_WINDOWS = "windows"
SOURCES = (SOURCE_NETWORK, SOURCE_USB, SOURCE_WINDOWS)  # USB incluye los COM


@dataclass(frozen=True)
class FoundPrinter:
    key: str
    title: str
    subtitle: str
    source: str
    candidate: object = None           # PrinterCandidate, o None si no se puede usar
    details: tuple = ()
    note: str = ""                     # aviso corto para la persona
    configured_as: str = ""
    hidden: bool = False
    hidden_reason: str = ""
    guide: str = ""                    # guía si no se puede usar
    rank: int = 5

    @property
    def selectable(self):
        return self.candidate is not None and not self.configured_as

    @property
    def transport(self):
        return getattr(self.candidate, "transport", "") if self.candidate is not None else ""


@dataclass
class SearchResult:
    network: object = None
    usb: object = None
    queues: object = None
    found: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    pending: set = field(default_factory=lambda: set(SOURCES))
    seconds: float = 0.0
    cancelled: bool = False

    @property
    def done(self):
        return not self.pending

    def visible(self, show_all=False):
        return [f for f in self.found if show_all or not f.hidden]

    @property
    def hidden_count(self):
        return sum(1 for f in self.found if f.hidden)


# -- Armar la lista ---------------------------------------------------------------

def _host_de_puerto(puerto):
    """192.168.1.50 de "IP_192.168.1.50", "192.168.1.50" o "192.168.1.50_1"."""
    m = re.match(r"^(?:IP_)?(\d+\.\d+\.\d+\.\d+)(?:_\d+)?$", puerto.strip(), re.I)
    if not m:
        return None
    try:
        return str(ipaddress.IPv4Address(m.group(1)))
    except ValueError:
        return None


def _de_red(p):
    marca = p.brand
    if p.model:
        titulo = p.model
    elif marca:
        titulo = f"Impresora {marca} de red"
    else:
        titulo = "Impresora de red"
    subtitulo = "Conectada a la red" if p.same_subnet else "Conectada a la red (otro rango del local)"
    detalles = [f"Dirección IP: {p.host}", f"Puerto: {p.port}"]
    if p.port != 9100:
        detalles[-1] += " (puerto de SAM4S)"
    if p.adapter is not None:
        detalles.append(f"Encontrada por: {p.adapter.label}")
    if p.mac:
        detalles.append(f"Placa de red: {p.mac_short}" + (f" ({marca})" if marca else ""))
    if p.snmp:
        detalles.append("Modelo informado por la impresora (SNMP)")
    if p.factory_brands:
        detalles.append("Tiene la IP de fábrica de: " + ", ".join(p.factory_brands))
    return FoundPrinter(key=f"network:{p.host}:{p.port}", title=titulo, subtitle=subtitulo,
                        source=SOURCE_NETWORK, candidate=p.candidate(), details=tuple(detalles),
                        rank=0 if p.same_subnet else 1)


def _de_usbprint(d):
    detalles = [f"USB {d.ids}",
                "Con número de serie" if d.serial else "Sin número de serie (se recuerda el puerto USB)"]
    if d.port_name:
        detalles.append(f"Puerto de Windows: {d.port_name}")
    detalles.append("Se usa directo, sin driver de impresora")
    return FoundPrinter(key=d.candidate().stable_id, title=d.title, subtitle="Conectada por USB",
                        source=SOURCE_USB, candidate=d.candidate(), details=tuple(detalles), rank=1)


def _de_com(p):
    detalles = [f"Puerto {p.device}, velocidad 9600"]
    if p.vendor_id is not None:
        detalles.append(f"USB {p.vendor_id:04X}:{p.product_id or 0:04X}" +
                        (f" (chip {p.chip})" if p.chip else ""))
    if p.description:
        detalles.append(p.description)
    oculta = p.hidden
    razon = {"bluetooth": "Es un puerto de Bluetooth", "modem": "Es un módem",
             "placa": "Es un puerto de la computadora, sin nada USB"}.get(p.kind, "")
    return FoundPrinter(key=f"serial:{p.device}", title=p.title,
                        subtitle="Conectada por cable USB" if p.kind == "usb" else "Puerto de la computadora",
                        source=SOURCE_SERIAL, candidate=p.candidate() if p.selectable else None,
                        details=tuple(detalles), hidden=oculta, hidden_reason=razon, rank=3)


def _de_cola(c):
    subtitulo = "Instalada en Windows"
    if c.shared_connection:
        subtitulo += ", compartida desde otra computadora"
    detalles = []
    if c.driver:
        detalles.append(f"Driver: {c.driver}")
    if c.port:
        detalles.append(f"Puerto: {c.port}")
    detalles.append(f"Estado según Windows: {c.status_text} (no confirma que imprima)")
    if c.is_default:
        detalles.append("Es la impresora predeterminada de Windows")
    razon = ""
    if c.virtual:
        razon = "No es una impresora de tickets (PDF, XPS, OneNote o fax)"
    elif c.offline:
        razon = "Windows la marca fuera de línea"
    nota = c.status_text if not c.hidden and not c.ready else ""
    return FoundPrinter(key=f"windows:{c.name.casefold()}", title=c.name, subtitle=subtitulo,
                        source=SOURCE_WINDOWS, candidate=c.candidate(), details=tuple(detalles),
                        note=nota, hidden=c.hidden, hidden_reason=razon, rank=2 + c.rank)


def _de_incompatible(i):
    from fiscalberry.common.usb_discovery import INCOMPATIBLE_WINUSB
    if i.reason == INCOMPATIBLE_WINUSB:
        nota = ("Tiene instalado un driver especial que Fiscalberry no usa. "
                "No se cambia nada: seguí la guía.")
    else:
        nota = ("Windows no la reconoce. Hace falta el driver del fabricante: "
                "seguí la guía.")
    detalles = [f"USB {i.ids}"]
    if i.service:
        detalles.append(f"Driver actual: {i.service}")
    if i.description:
        detalles.append(i.description)
    return FoundPrinter(key=f"incompatible:{i.ids}", title=i.title, subtitle="Conectada por USB",
                        source=SOURCE_USB, candidate=None, details=tuple(detalles), note=nota,
                        guide=GUIDE_USB_DRIVER, rank=6)


def merge(network=None, usb=None, queues=None, service=None):
    """(encontradas, avisos) a partir de lo que devolvió cada fuente."""
    encontradas = []
    avisos = []

    colas = list(getattr(queues, "queues", None) or [])
    colas_visibles = [c for c in colas if not c.hidden]
    puertos_usb = {}
    puertos_com = {}
    for c in colas_visibles:
        for p in c.usb_ports:
            puertos_usb.setdefault(p, c.name)
        for p in c.com_ports:
            puertos_com.setdefault(p, c.name)

    hosts_red = set()
    if network is not None:
        for p in network.printers:
            encontradas.append(_de_red(p))
            hosts_red.add(p.host)
        avisos += list(network.notes)
        if network.error:
            avisos.append(network.error)

    if usb is not None:
        for d in usb.usbprint:
            item = _de_usbprint(d)
            cola = puertos_usb.get(d.port_name.upper()) if d.port_name else None
            if cola:
                item = replace(item, hidden=True,
                               hidden_reason=f"Es la misma impresora que la cola \"{cola}\"")
            encontradas.append(item)
        for p in usb.serial:
            item = _de_com(p)
            cola = puertos_com.get(p.device.upper())
            if cola and not item.hidden:
                item = replace(item, hidden=True,
                               hidden_reason=f"Es la misma impresora que la cola \"{cola}\"")
            encontradas.append(item)
        for i in usb.incompatible:
            encontradas.append(_de_incompatible(i))
        avisos += list(usb.errors)

    for c in colas:
        item = _de_cola(c)
        hosts = {_host_de_puerto(p) for p in c.ports} - {None}
        misma_red = hosts & hosts_red
        if misma_red and not item.hidden:
            item = replace(item, hidden=True, hidden_reason=(
                f"Es la misma impresora que {sorted(misma_red)[0]}, que se usa directo por la red"))
        encontradas.append(item)
    if queues is not None and getattr(queues, "message", ""):
        avisos.append(queues.message)

    if service is not None:
        marcadas = []
        for f in encontradas:
            if f.candidate is None:
                marcadas.append(f)
                continue
            try:
                alias = service.find_duplicate(f.candidate)
            except Exception as e:
                logger.debug(f"No se pudo comparar con las configuradas: {e}")
                alias = None
            marcadas.append(replace(f, configured_as=alias) if alias else f)
        encontradas = marcadas

    encontradas.sort(key=lambda f: (f.hidden, bool(f.configured_as), f.rank, f.title.casefold()))
    return encontradas, list(dict.fromkeys(a for a in avisos if a))


# -- La búsqueda ------------------------------------------------------------------

class PrinterSearch:
    """Corre las tres fuentes en paralelo. Inyectables para los tests."""

    def __init__(self, service=None, network=None, usb=None, queues=None):
        self.service = service
        self._network = network
        self._usb = usb
        self._queues = queues

    def _fuentes(self):
        network = self._network
        if network is None:
            from fiscalberry.common.network_discovery import search_network as network
        usb = self._usb
        if usb is None:
            from fiscalberry.common.usb_discovery import search_usb

            def usb(cancel=None):
                return search_usb()
        queues = self._queues
        if queues is None:
            from fiscalberry.common.windows_queues import list_queues as queues
        return {SOURCE_NETWORK: network, SOURCE_USB: usb, SOURCE_WINDOWS: queues}

    def run(self, cancel=None, on_partial=None, clock=time.monotonic):
        cancel = cancel or threading.Event()
        inicio = clock()
        resultado = SearchResult()
        lock = threading.Lock()
        terminadas = threading.Event()

        def rearmar():
            resultado.found, resultado.notes = merge(resultado.network, resultado.usb,
                                                     resultado.queues, self.service)

        def correr(nombre, fn):
            try:
                valor = fn(cancel=cancel)
            except Exception as e:  # una fuente rota no tapa a las demás
                logger.error(f"Búsqueda de impresoras ({nombre}) falló: {e}", exc_info=True)
                valor = None
            with lock:
                if nombre == SOURCE_NETWORK:
                    resultado.network = valor
                elif nombre == SOURCE_USB:
                    resultado.usb = valor
                else:
                    resultado.queues = valor
                resultado.pending.discard(nombre)
                rearmar()
                if valor is None:
                    resultado.notes.append({
                        SOURCE_NETWORK: "No se pudo revisar la red.",
                        SOURCE_USB: "No se pudieron revisar las impresoras USB.",
                        SOURCE_WINDOWS: "No se pudieron leer las impresoras instaladas en Windows.",
                    }[nombre])
                resultado.seconds = clock() - inicio
                parcial = _copia(resultado)
                if not resultado.pending:
                    terminadas.set()
            if on_partial is not None and not cancel.is_set():
                try:
                    on_partial(parcial)
                except Exception as e:
                    logger.debug(f"Error mostrando resultados parciales: {e}")

        hilos = [threading.Thread(target=correr, args=(n, fn), daemon=True,
                                  name=f"fiscalberry-busqueda-{n}")
                 for n, fn in self._fuentes().items()]
        for h in hilos:
            h.start()
        while not terminadas.wait(0.1):
            if cancel.is_set():
                break
        with lock:
            resultado.cancelled = cancel.is_set()
            resultado.seconds = clock() - inicio
            final = _copia(resultado)
        logger.info("Búsqueda de impresoras: %d encontradas (%d ocultas) en %.1f s%s",
                    len(final.found), final.hidden_count, final.seconds,
                    " (cancelada)" if final.cancelled else "")
        return final


def _copia(r):
    return SearchResult(network=r.network, usb=r.usb, queues=r.queues, found=list(r.found),
                        notes=list(r.notes), pending=set(r.pending), seconds=r.seconds,
                        cancelled=r.cancelled)


def find(found, key) -> Optional[FoundPrinter]:
    return next((f for f in found if f.key == key), None)
