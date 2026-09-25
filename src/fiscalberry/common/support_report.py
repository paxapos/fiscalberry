"""
Diagnóstico del asistente de impresoras para soporte (#185).

Un texto que la persona copia y pega en el chat de soporte. Tiene que servir
para reproducir el paso exacto donde falló, sin exponer nada que no haga
falta:

- **Se arma solo con campos permitidos** (nada de volcar el config.ini): la
  versión, el sistema, el comercio, el nivel de privilegio, el estado del
  servicio, las redes de la PC, lo que encontró la búsqueda, la última
  prueba (transporte, DLE EOT, LPT), la dirección escrita y su diagnóstico,
  las impresoras configuradas y el recorrido paso a paso.
- **Se reduce lo identificable**: de una MAC queda el fabricante
  (`00:26:AB:xx:xx:xx`); de un número de serie, los últimos 4; una IP
  pública se oculta (las privadas del local quedan: sin ellas no se entiende
  un problema de subred); la carpeta del usuario se reemplaza por `~`; el
  id del equipo queda en 4 caracteres.
- **Nunca** credenciales MQTT, JWT, contraseñas, tokens ni tickets. Además de
  no incluirlos, una pasada final reemplaza cualquier valor secreto del
  config.ini y todo lo que parezca un JWT o un token por "[oculto]".
- Del registro solo entran advertencias y errores de los módulos del
  asistente (nunca el contenido de un ticket).

El escenario 5 (IP temporal, dhcpstaticipcoexistence, fallback, diario de
red) es de la fase 3: el reporte lo dice explícitamente.
"""

import ipaddress
import os
import platform as _platform
import re
import sys
import time
from datetime import datetime

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("SupportReport")

HIDDEN = "[oculto]"

# Nombres de clave del config.ini cuyo valor nunca puede aparecer.
_SENSITIVE_KEY = re.compile(r"(pass|token|jwt|secret|key|credential|auth|cookie|session|"
                            r"^user(name)?$|_user$|usuario)", re.I)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_BEARER = re.compile(r"(?i)\b(bearer|token|jwt|password|passwd|pwd|secret)\b(\s*[:=]\s*|\s+)"
                     r"[\"']?[^\s\"',;]+")
_MAC = re.compile(r"\b([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")

# Loggers del asistente cuyas advertencias y errores entran al reporte.
_WIZARD_LOGGERS = ("PrinterWizard", "PrinterTest", "PrinterSearch", "NetworkDiscovery",
                   "UsbDiscovery", "UsbPrint", "WindowsQueues", "GUI.PrinterSetup",
                   "SupportReport")
_LOG_LINE = re.compile(r"\b(WARNING|ERROR|CRITICAL)\s+(" +
                       "|".join(re.escape(n) for n in _WIZARD_LOGGERS) + r")\b")
MAX_LOG_LINES = 20
MAX_LINE = 300

# Qué claves de una impresora configurada se muestran.
_PRINTER_KEYS = ("driver", "host", "port", "printer_name", "devfile", "baudrate",
                 "idVendor", "idProduct", "serial_number", "_setup_id")


# -- Reducción ----------------------------------------------------------------

def redact_ip(ip):
    try:
        direccion = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return str(ip)
    if direccion.is_private or direccion.is_loopback or direccion.is_link_local:
        return str(direccion)
    return "IP pública (oculta)"


def redact_mac(mac):
    mac = str(mac or "").strip().upper().replace("-", ":")
    if not _MAC.fullmatch(mac):
        return ""
    return mac[:8] + ":xx:xx:xx"


def redact_serial(serial):
    serial = str(serial or "").strip()
    if not serial:
        return ""
    return "…" + serial[-4:] if len(serial) > 4 else "…"


def redact_identity(identidad):
    """usbprint:04b8:0e15:X4TK001234 -> usbprint:04b8:0e15:…1234 (y afines)."""
    texto = str(identidad or "")
    m = re.match(r"^(usbprint|serial|usb):([0-9a-f]{4}):([0-9a-f]{4}):(.+)$", texto, re.I)
    if m:
        return f"{m.group(1)}:{m.group(2)}:{m.group(3)}:{redact_serial(m.group(4))}"
    m = re.match(r"^network:([^:]+):(\d+)$", texto)
    if m:
        return f"network:{redact_ip(m.group(1))}:{m.group(2)}"
    return texto


def _redactar(valor):
    if isinstance(valor, dict):
        return {k: _redactar(v) for k, v in valor.items() if not _SENSITIVE_KEY.search(str(k))}
    if isinstance(valor, (list, tuple)):
        return [_redactar(v) for v in valor]
    if isinstance(valor, str):
        texto = redact_identity(valor)
        return _MAC.sub(lambda m: redact_mac(m.group(0)), texto)
    return valor


def _sin_home(texto):
    home = os.path.expanduser("~")
    if home and len(home) > 3:
        texto = texto.replace(home, "~")
    return re.sub(r"(?i)([A-Z]:\\Users\\)[^\\]+", r"\1<usuario>", texto)


def secret_values(config_data):
    """Valores del config.ini que nunca pueden aparecer (claves sensibles)."""
    secretos = set()
    for seccion, valores in (config_data or {}).items():
        if not isinstance(valores, dict):
            continue
        for clave, valor in valores.items():
            valor = str(valor or "").strip()
            if len(valor) >= 4 and _SENSITIVE_KEY.search(str(clave)):
                secretos.add(valor)
    return secretos


def scrub(texto, secretos=()):
    """Última pasada: fuera cualquier secreto conocido, JWT o token."""
    for s in sorted(secretos, key=len, reverse=True):
        texto = texto.replace(s, HIDDEN)
    texto = _JWT.sub(HIDDEN, texto)
    texto = _BEARER.sub(lambda m: f"{m.group(1)}{m.group(2)}{HIDDEN}", texto)
    # Toda IPv4 pública (en el recorrido, en el registro): oculta. Las privadas
    # del local quedan.
    texto = _IPV4.sub(lambda m: redact_ip(m.group(0)), texto)
    return _sin_home(texto)


# -- Datos del entorno --------------------------------------------------------

def _version():
    try:
        from fiscalberry.version import VERSION
        return VERSION
    except Exception:
        return "desconocida"


def _instalacion():
    try:
        from fiscalberry.common.updater import install_kind
        return str(install_kind.detect())
    except Exception:
        return "desconocida"


def _sistema():
    try:
        if sys.platform == "win32":
            version = sys.getwindowsversion()
            nombre = "Windows 11" if version.build >= 22000 else f"Windows {_platform.release()}"
            return f"{nombre} (build {version.build}), {_platform.machine()}"
        return f"{_platform.system()} {_platform.release()}, {_platform.machine()}"
    except Exception:
        return sys.platform


def _servicio():
    try:
        from fiscalberry.common.service_status import read_status
        estado = read_status()
    except Exception:
        estado = None
    if not estado:
        return "sin datos recientes del servicio"
    return ("conectado al servidor" if estado.get("sio_connected") else "sin conexión al servidor") + \
        f" (MQTT: {'sí' if estado.get('mqtt_connected') else 'no'})"


def _lineas_de_log(ruta=None, max_bytes=65536):
    try:
        from fiscalberry.common.fiscalberry_logger import readLogTail
        texto = readLogTail(max_bytes=max_bytes, path=ruta)
    except Exception:
        return []
    lineas = [l.strip()[:MAX_LINE] for l in texto.splitlines() if _LOG_LINE.search(l)]
    return lineas[-MAX_LOG_LINES:]


# -- Armado -------------------------------------------------------------------

def _si_no(valor):
    return "sí" if valor else "no"


def _estado_dle(estado):
    if not estado or estado.get("online") is None:
        return "sin respuesta (la impresora no informa su estado)"
    nombres = (("online", "en línea"), ("cover_open", "tapa abierta"), ("paper_out", "sin papel"),
               ("paper_near_end", "poco papel"), ("error", "error"))
    return ", ".join(f"{texto}={'?' if estado.get(k) is None else _si_no(estado.get(k))}"
                     for k, texto in nombres)


def _adaptadores(w):
    r = getattr(w, "search_result", None)
    if r is not None and r.network is not None and r.network.adapters:
        return r.network.adapters
    fn = getattr(w, "_list_adapters", None)
    if fn is not None:
        try:
            return fn()
        except Exception:
            return []
    try:
        from fiscalberry.common.network_discovery import list_adapters
        return list_adapters()
    except Exception:
        return []


_TIPOS_ADAPTADOR = {"fisico": "físico", "vpn": "VPN", "virtual": "virtual", "loopback": "loopback"}


def _conexion(candidato):
    """La conexión como en el ticket, pero con el número de serie reducido."""
    from fiscalberry.common.printer_setup import CONNECTION_LABELS, TRANSPORT_USB, TRANSPORT_USBPRINT
    etiqueta = CONNECTION_LABELS.get(candidato.transport, candidato.transport or "Impresora")
    detalle = candidato.detail
    if candidato.transport in (TRANSPORT_USBPRINT, TRANSPORT_USB):
        detalle = redact_serial(detalle)
    elif detalle:
        detalle = re.sub(r"\d+\.\d+\.\d+\.\d+", lambda m: redact_ip(m.group(0)), detalle)
    return f"{etiqueta} ({detalle})" if detalle else etiqueta


def _linea_encontrada(f):
    partes = [f"[{f.transport or 'no se puede usar'}] {f.title}"]
    tecnico = [d for d in f.details if d.startswith(("Dirección IP", "Puerto", "USB ", "Puerto de Windows",
                                                     "Con número", "Sin número", "Driver",
                                                     "Placa de red", "Tiene la IP de fábrica"))]
    if tecnico:
        partes.append(" — " + "; ".join(tecnico))
    if f.configured_as:
        partes.append(f" (configurada como {f.configured_as})")
    if f.hidden:
        partes.append(f" (oculta: {f.hidden_reason})")
    if f.note:
        partes.append(f" — {f.note}")
    return "- " + "".join(partes)


def collect_lines(wizard=None, config_data=None, now=None, version=None, installation=None,
                  system=None, privilege=None, service=None, log_lines=None, adapters=None):
    """Las líneas del reporte, antes de la pasada final de secretos."""
    from fiscalberry.common.printer_guides import guide_url
    from fiscalberry.common.windows_privilege import DESCRIPTIONS, detect_privilege

    w = wizard
    datos = config_data or {}
    ahora = now or datetime.now()
    privilegio = privilege or detect_privilege()
    lineas = [
        "DIAGNÓSTICO DEL ASISTENTE DE IMPRESORAS — Fiscalberry",
        f"Generado: {ahora:%Y-%m-%d %H:%M:%S}",
        f"Versión: {version or _version()} ({installation or _instalacion()})",
        f"Sistema: {system or _sistema()}",
        f"Permisos: {DESCRIPTIONS.get(privilegio, privilegio)}",
    ]

    paxa = next((v for k, v in datos.items() if k.lower() == "paxaprinter"), {}) or {}
    servidor = next((v for k, v in datos.items() if k.lower() == "servidor"), {}) or {}
    comercio = paxa.get("site_name") or paxa.get("alias") or (w.commerce if w else "") or "sin nombre"
    vinculado = bool(str(paxa.get("tenant", "")).strip())
    lineas.append(f"Comercio: {comercio} ({'vinculado' if vinculado else 'sin vincular'})")
    uuid = str(servidor.get("uuid", "")).strip()
    if uuid:
        lineas.append(f"Equipo: id {redact_serial(uuid)}")
    lineas.append(f"Servicio: {service or _servicio()}")

    # -- dónde quedó
    lineas += ["", "== Dónde quedó"]
    if w is None:
        lineas.append("El asistente no se abrió en esta sesión.")
    else:
        lineas.append(f"Paso actual: {w.step}")
        if w.message:
            lineas.append(f"Mensaje: {w.message}")
        if w.guide:
            lineas.append(f"Guía ofrecida: {guide_url(w.guide)}")
        if w.saved:
            lineas.append("Guardadas en esta sesión: " + ", ".join(w.saved))

    # -- última prueba
    if w is not None and w.candidate is not None:
        c = w.candidate
        r = w.result or getattr(w, "last_result", None)
        lineas += ["", "== Última prueba",
                   f"Impresora: {c.display_name} ({c.transport})",
                   f"Identidad: {redact_identity(c.stable_id)}",
                   f"Conexión: {_conexion(c)}"]
        if r is None:
            lineas.append("Resultado: sin terminar")
        else:
            lineas.append("Resultado técnico: " + ("bien" if r.technical_success
                                                   else f"falló ({r.problem})"))
            if r.detail:
                lineas.append(f"Detalle: {_redactar(r.detail)[:MAX_LINE]}")
            estado = r.status_after if r.status_after.known else r.status_before
            lineas.append(f"Estado DLE EOT: {_estado_dle(estado.as_dict())}")
            if r.lpt_status:
                lineas.append("Estado LPT (informativo): " +
                              ", ".join(f"{k}={_si_no(v)}" for k, v in r.lpt_status.items()))
            if r.tracker is not None:
                lineas.append(f"Trabajo de prueba borrado de la cola: {_si_no(r.job_cancelled)}")
            lineas.append(f"Papel confirmado: {_si_no(r.paper_confirmed)}")

    # -- dirección escrita
    d = getattr(w, "diagnosis", None) if w is not None else None
    if d is not None:
        lineas += ["", "== Dirección escrita",
                   f"{redact_ip(d.host)}:{d.port} -> {d.kind} (TCP: {d.tcp})"]
        if d.brands:
            lineas.append("IP de fábrica de: " + ", ".join(d.brands))
        if d.local_networks:
            lineas.append("Redes de la PC: " + ", ".join(d.local_networks))
        if d.is_gateway:
            lineas.append("Es la dirección del router")

    # -- búsqueda
    r = getattr(w, "search_result", None) if w is not None else None
    if r is not None:
        lineas += ["", "== Búsqueda",
                   f"Duración: {r.seconds:.1f} s; encontradas: {len(r.found)} "
                   f"({r.hidden_count} ocultas){'; cancelada' if r.cancelled else ''}"
                   f"{'; incompleta: ' + ', '.join(sorted(r.pending)) if r.pending else ''}"]
        if r.network is not None:
            lineas.append(f"Red: {r.network.swept} direcciones revisadas en {r.network.seconds:.1f} s"
                          + (f"; error: {r.network.error}" if r.network.error else ""))
        if r.usb is not None:
            lineas.append(f"USB: {len(r.usb.usbprint)} por usbprint, {len(r.usb.serial)} puertos COM, "
                          f"{len(r.usb.incompatible)} incompatibles")
        if r.queues is not None:
            q = r.queues
            if q.skipped:
                lineas.append("Colas de Windows: no aplica")
            else:
                lineas.append(f"Colas de Windows: {len(q.queues)} en {q.seconds:.1f} s; "
                              f"venció: {_si_no(q.timed_out)}; solo locales: {_si_no(q.local_only)}"
                              + (f"; error: {q.error}" if q.error else ""))
        if r.notes:
            lineas.append("Avisos:")
            lineas += [f"- {n}" for n in r.notes]
        if r.found:
            lineas.append("Impresoras:")
            lineas += [_linea_encontrada(f) for f in r.found]

    # -- redes de la PC
    adaptadores = adapters if adapters is not None else (_adaptadores(w) if w is not None else [])
    if adaptadores:
        lineas += ["", "== Redes de la PC"]
        for a in adaptadores:
            if a.kind == "loopback":
                continue
            red = f"{redact_ip(a.address)}/{a.prefix}" if a.prefix is not None \
                else f"{redact_ip(a.address)} (máscara {a.raw_netmask or '?'})"
            tipo = _TIPOS_ADAPTADOR.get(a.kind, a.kind)
            partes = [f"- {a.label} ({tipo}{', conectado' if a.up else ', desconectado'}): {red}"]
            if a.gateways:
                partes.append("gateway " + ", ".join(redact_ip(g) for g in a.gateways))
            if a.dhcp is not None:
                partes.append(f"DHCP {_si_no(a.dhcp)}")
            if a.mac and redact_mac(a.mac):
                partes.append(f"placa {redact_mac(a.mac)}")
            if not a.usable:
                partes.append("no se revisa")
            lineas.append("; ".join(partes))

    lineas += ["", "== Escenario 5 (otra subred con IP temporal)",
               "No disponible en esta versión: no se usó IP temporal, ni "
               "dhcpstaticipcoexistence, ni el fallback de #178; no hay diario de red."]

    # -- impresoras configuradas
    from fiscalberry.common.printer_setup import PrinterSetupService, is_valid_printer_config
    configuradas = [(s, v) for s, v in datos.items()
                    if s.lower() not in PrinterSetupService.RESERVED_SECTIONS
                    and is_valid_printer_config(v)]
    lineas += ["", "== Impresoras configuradas"]
    if not configuradas:
        lineas.append("Ninguna")
    for seccion, valores in configuradas:
        campos = []
        for clave in _PRINTER_KEYS:
            valor = next((v for k, v in valores.items() if k.lower() == clave.lower()), None)
            if valor in (None, ""):
                continue
            if clave == "host":
                valor = redact_ip(valor)
            elif clave == "serial_number":
                valor = redact_serial(valor)
            elif clave == "_setup_id":
                valor = redact_identity(valor)
            campos.append(f"{clave}={valor}")
        lineas.append(f"- {seccion}: " + ", ".join(campos))

    # -- recorrido
    if w is not None and w.journal:
        lineas += ["", "== Recorrido"]
        t0 = w.journal[0]["t"]
        for e in w.journal:
            extra = {k: v for k, v in e.items() if k not in ("t", "paso", "evento")
                     and v not in (None, "", [], {})}
            extra = _redactar(extra)
            detalle = " ".join(f"{k}={v}" for k, v in extra.items())
            lineas.append(f"+{e['t'] - t0:.1f} s {e['paso']} · {e['evento']}"
                          + (f" {detalle}" if detalle else ""))

    # -- registro
    log = log_lines if log_lines is not None else _lineas_de_log()
    lineas += ["", "== Errores recientes del asistente"]
    lineas += log or ["Ninguno"]
    return lineas


def build_report(wizard=None, config_data=None, **kwargs):
    """El reporte listo para copiar. Nunca lanza."""
    try:
        if config_data is None:
            from fiscalberry.common.Configberry import Configberry
            config_data = Configberry().get_actual_config()
    except Exception:
        config_data = {}
    try:
        texto = "\n".join(collect_lines(wizard, config_data, **kwargs))
    except Exception as e:
        logger.error(f"No se pudo armar el diagnóstico completo: {e}", exc_info=True)
        texto = (f"DIAGNÓSTICO DEL ASISTENTE DE IMPRESORAS — Fiscalberry\n"
                 f"Versión: {_version()}\nNo se pudo armar el diagnóstico completo: "
                 f"{type(e).__name__}")
    return scrub(texto, secret_values(config_data))


def save_report(texto, carpeta=None, clock=time.time):
    """Guarda el reporte junto al registro. Devuelve la ruta o "" si no se pudo."""
    try:
        if carpeta is None:
            from fiscalberry.common.fiscalberry_logger import getLogFilePath
            ruta_log = getLogFilePath()
            carpeta = os.path.dirname(ruta_log) if ruta_log else None
        if not carpeta:
            return ""
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, "diagnostico-impresoras.txt")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(texto)
        return ruta
    except Exception as e:
        logger.warning(f"No se pudo guardar el diagnóstico: {e}")
        return ""
