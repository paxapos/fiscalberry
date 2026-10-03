"""
Lo que el asistente de impresoras ve en esta PC, en JSON.

    fiscalberry-gui.exe --discovery-report --report <archivo.json>

Solo lee: no barre la red, no abre impresoras ni imprime. Lo corre la prueba
del instalador en un Windows real de la CI (sin impresoras) para comprobar que
las APIs de Windows que el asistente llama por ctypes (GetAdaptersAddresses,
GetIpNetTable, SetupDi de usbprint, cfgmgr32) no revientan y devuelven datos
con la forma esperada: un struct mal declarado no lo detecta ningún test en
Linux. Soporte también lo puede pedir.

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
    # Solo cuántas: las MAC de los equipos de la red no hacen falta acá.
    return {"entradas": len(read_arp_table())}


def _usbprint():
    from fiscalberry.common.usb_discovery import list_usbprint_devices
    # Sin abrir los dispositivos: el informe solo lee.
    return [dict(ruta=d.device_path, ids=d.ids, con_serie=bool(d.serial), puerto=d.port_name,
                 descripcion=d.bus_description)
            for d in list_usbprint_devices(with_details=False)]


def _dispositivos_usb():
    if sys.platform != "win32":
        return {}
    from fiscalberry.common.usb_discovery import windows_usb_devices
    dispositivos = windows_usb_devices()
    return {"total": len(dispositivos),
            "con_problema": sum(1 for d in dispositivos if d["problem"]),
            "servicios": sorted({d["service"] for d in dispositivos if d["service"]})}


# Así empieza la ruta de una interfaz de dispositivo: \\?\
_PREFIJO_RUTA = "\\\\?\\"


def _control_setupdi():
    """
    La CI no tiene impresoras ni USB: que usbprint y los USB den cero no
    prueba nada. Con el mismo código se enumeran los discos (interfaces) y
    todos los dispositivos, que en cualquier PC son más de cero.
    """
    if sys.platform != "win32":
        return {}
    from fiscalberry.common.usb_discovery import (GUID_DEVINTERFACE_DISK, parse_device_path,
                                                  windows_device_interfaces, windows_usb_devices)
    discos = windows_device_interfaces(GUID_DEVINTERFACE_DISK)
    todos = windows_usb_devices(enumerador=None)
    return {"interfaces_de_disco": len(discos),
            "rutas_legibles": sum(1 for ruta, _, _ in discos if ruta.startswith(_PREFIJO_RUTA)),
            "dispositivos": len(todos),
            "con_hardware_id": sum(1 for d in todos if d["hardware_ids"]),
            "usb_en_rutas": sum(1 for ruta, _, _ in discos if parse_device_path(ruta))}


def _puertos_com():
    from fiscalberry.common.usb_discovery import list_serial_ports
    return [dict(puerto=p.device, tipo=p.kind, descripcion=p.description)
            for p in list_serial_ports()]


def _colas_windows():
    if sys.platform != "win32":
        return []
    from fiscalberry.common.windows_queues import listar_colas
    # Por el mismo subproceso (--list-printers) que usa el asistente.
    r = listar_colas()
    if r.error:
        raise RuntimeError(f"{r.error}: {r.detalle}")
    return [dict(nombre=c.nombre, puerto=c.puerto, driver=c.driver, local=c.local,
                 virtual=c.virtual, fuera_de_linea=c.fuera_de_linea) for c in r.colas]


SECTIONS = {
    "adaptadores": _adaptadores,
    "arp": _arp,
    "usbprint": _usbprint,
    "dispositivos_usb": _dispositivos_usb,
    "control_setupdi": _control_setupdi,
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
