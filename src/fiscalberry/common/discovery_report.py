"""
Lo que el asistente de impresoras ve en esta PC, en JSON.

    fiscalberry-gui.exe --discovery-report --report <archivo.json>

Solo lee: no barre la red, no abre impresoras ni imprime. Lo corre la prueba
del instalador en un Windows real de la CI (sin impresoras) para comprobar
que las APIs de Windows que usa el asistente no revientan y devuelven datos
con la forma esperada; soporte también lo puede pedir.

Cada sección se arma por separado: si una falla, queda su error y las demás
siguen. El código de salida es 1 si alguna falló.
"""

import json
import sys
from dataclasses import asdict


def _adaptadores():
    from fiscalberry.common.network_discovery import list_adapters
    return [asdict(a) for a in list_adapters()]


def _arp():
    from fiscalberry.common.network_discovery import read_arp_table
    return {"entradas": len(read_arp_table())}


def _usbprint():
    from fiscalberry.common.usb_discovery import list_usbprint_devices
    # Sin abrir los dispositivos: el informe solo lee.
    return [dict(ruta=d.device_path, vid=d.ids, serie=bool(d.serial), puerto=d.port_name,
                 descripcion=d.bus_description)
            for d in list_usbprint_devices(with_details=False)]


def _dispositivos_usb():
    from fiscalberry.common.usb_discovery import windows_usb_devices
    if sys.platform != "win32":
        return []
    dispositivos = windows_usb_devices()
    return {"total": len(dispositivos),
            "con_problema": sum(1 for d in dispositivos if d["problem"]),
            "servicios": sorted({d["service"] for d in dispositivos if d["service"]})}


def _puertos_com():
    from fiscalberry.common.usb_discovery import list_serial_ports
    return [dict(puerto=p.device, tipo=p.kind, descripcion=p.description)
            for p in list_serial_ports()]


def _colas_windows():
    from fiscalberry.common.windows_queues import list_queues
    # Por el mismo subproceso (--list-printers) que usa el asistente.
    r = list_queues()
    if r.skipped:
        return []
    if r.error and not r.queues:
        raise RuntimeError(r.error)
    return {"segundos": round(r.seconds, 2), "vencido": r.timed_out, "solo_locales": r.local_only,
            "colas": [dict(nombre=c.name, puerto=c.port, driver=c.driver, tipo=c.kind,
                           oculta=c.hidden, estado=c.status_text) for c in r.queues]}


SECTIONS = {
    "adaptadores": _adaptadores,
    "arp": _arp,
    "usbprint": _usbprint,
    "dispositivos_usb": _dispositivos_usb,
    "puertos_com": _puertos_com,
    "colas_windows": _colas_windows,
}


def build_report(sections=None):
    """(informe, fallas). Nunca lanza."""
    informe = {"plataforma": sys.platform}
    fallas = []
    for nombre, fn in (sections or SECTIONS).items():
        try:
            informe[nombre] = fn()
        except Exception as e:  # una sección rota no tapa a las demás
            informe[nombre] = {"error": f"{type(e).__name__}: {e}"}
            fallas.append(nombre)
    informe["fallas"] = fallas
    return informe, fallas


def run(ruta_reporte=None, sections=None):
    informe, fallas = build_report(sections)
    texto = json.dumps(informe, ensure_ascii=False, indent=2, default=str)
    if ruta_reporte:
        with open(ruta_reporte, "w", encoding="utf-8") as fh:
            fh.write(texto)
    else:
        print(texto)
    return 1 if fallas else 0
