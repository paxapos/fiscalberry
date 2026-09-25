"""
Impresoras USB y puertos COM de Windows (#183, escenarios 2 y 3).

Sin admin y sin tocar drivers:

- **usbprint** (`list_usbprint_devices`): las interfaces
  GUID_DEVINTERFACE_USBPRINT que publica usbprint.sys para toda impresora de
  clase USB 0x07, tenga o no driver de impresora y cola. De la ruta del
  dispositivo salen VID, PID y número de serie; el modelo, del Device ID IEEE
  1284 (IOCTL) o de la descripción que reporta el bus. También el puerto
  USB00x, para reconocer la cola de Windows que usa esa misma impresora.
- **COM** (`list_serial_ports`): pyserial. USB-serie (CDC con usbser.sys,
  CH340, PL2303, FTDI, CP210x) aparece con VID/PID. Los COM de Bluetooth no se
  abren nunca (abrirlos dispara una conexión que puede colgar); los COM de la
  placa madre y los módems se ocultan por defecto.
- **Incompatibles** (`find_incompatible_usb`): una impresora de una marca
  conocida que Windows no reconoce (sin driver) o que alguien pasó a WinUSB /
  libusb (Zadig). **No se modifica nada**: se muestra la alternativa segura
  con el enlace a la guía.

Las APIs de Windows (setupapi, cfgmgr32, registro) van detrás de funciones
inyectables; los tests usan salidas simuladas.
"""

import re
import sys
from dataclasses import dataclass, field, replace

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("UsbDiscovery")

GUID_DEVINTERFACE_USBPRINT = "{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"

# VID -> marca. Solo para mostrar un nombre si el dispositivo no dice su modelo.
USB_VENDORS = {
    0x04B8: "Epson",
    0x0519: "Star Micronics",
    0x1504: "Bixolon",
    0x1D90: "Citizen",
    0x0DD4: "Custom",
    0x154F: "SNBC",
}
# Chips USB-serie: el VID es del chip, no de la impresora.
USB_SERIAL_CHIPS = {
    0x1A86: "CH340",
    0x067B: "Prolific",
    0x0403: "FTDI",
    0x10C4: "Silicon Labs",
}

# ruta: \\?\usb#vid_04b8&pid_0e15[&mi_00]#<instancia>#{guid}
_RUTA = re.compile(r"vid_([0-9a-f]{4})&pid_([0-9a-f]{4})(&mi_[0-9a-f]{2})?#([^#]*)#", re.I)


def parse_device_path(path):
    """(vid, pid, serie) de la ruta de una interfaz USB, o None."""
    m = _RUTA.search(str(path or ""))
    if not m:
        return None
    instancia = m.group(4)
    # Sin número de serie Windows inventa una instancia ("6&2c5b3a7&0&1") y en
    # un dispositivo compuesto (&mi_00) la instancia es de la interfaz: en los
    # dos casos no hay serie que sirva de identidad.
    serie = "" if (m.group(3) or "&" in instancia) else instancia
    return int(m.group(1), 16), int(m.group(2), 16), serie


@dataclass(frozen=True)
class UsbPrintDevice:
    device_path: str
    vendor_id: int
    product_id: int
    serial: str = ""
    port_name: str = ""          # "USB001": el puerto que usaría una cola de Windows
    bus_description: str = ""    # lo que la impresora dice ser por USB
    ieee1284: dict = field(default_factory=dict)

    @property
    def model(self):
        from fiscalberry.common.usbprint_driver import model_from_1284
        return model_from_1284(self.ieee1284) or self.bus_description.strip()

    @property
    def title(self):
        if self.model:
            return self.model
        marca = USB_VENDORS.get(self.vendor_id)
        return f"Impresora USB {marca}" if marca else "Impresora USB"

    @property
    def ids(self):
        return f"{self.vendor_id:04X}:{self.product_id:04X}"

    def candidate(self):
        from fiscalberry.common.printer_setup import PrinterCandidate
        c = PrinterCandidate.usbprint(self.device_path, self.vendor_id, self.product_id, self.serial)
        return replace(c, display_name=self.title)


@dataclass(frozen=True)
class SerialPort:
    device: str               # "COM3"
    description: str = ""
    hwid: str = ""
    vendor_id: object = None
    product_id: object = None
    serial_number: str = ""
    manufacturer: str = ""
    kind: str = "usb"         # usb, bluetooth, placa, modem

    @property
    def hidden(self):
        """Solo los USB se muestran de entrada (los demás, con "mostrar todas")."""
        return self.kind != "usb"

    @property
    def selectable(self):
        # Un COM de Bluetooth no se abre nunca: puede colgar buscando el equipo.
        return self.kind != "bluetooth"

    @property
    def title(self):
        if self.vendor_id in USB_VENDORS:
            return f"Impresora USB {USB_VENDORS[self.vendor_id]} ({self.device})"
        if self.kind == "usb":
            return f"Impresora USB ({self.device})"
        return f"Puerto {self.device}"

    @property
    def chip(self):
        return USB_SERIAL_CHIPS.get(self.vendor_id, "")

    def candidate(self):
        from fiscalberry.common.printer_setup import PrinterCandidate
        c = PrinterCandidate.serial(self.device, vendor_id=self.vendor_id,
                                    product_id=self.product_id, serial_number=self.serial_number)
        return replace(c, display_name=self.title)


# -- COM (escenario 3) ------------------------------------------------------------

def classify_serial_port(device, description="", hwid="", vendor_id=None):
    texto = f"{description} {hwid}".upper()
    if "BTHENUM" in texto or "BLUETOOTH" in texto:
        return "bluetooth"
    if "MODEM" in texto or "MÓDEM" in texto:
        return "modem"
    if vendor_id is not None or "USB" in texto:
        return "usb"
    return "placa"


def list_serial_ports(comports=None):
    """Puertos COM con su VID/PID (pyserial). Nunca abre ninguno."""
    if comports is None:
        from serial.tools.list_ports import comports
    puertos = []
    for p in comports():
        vid = getattr(p, "vid", None)
        puertos.append(SerialPort(
            device=str(p.device),
            description=str(getattr(p, "description", "") or ""),
            hwid=str(getattr(p, "hwid", "") or ""),
            vendor_id=vid,
            product_id=getattr(p, "pid", None),
            serial_number=str(getattr(p, "serial_number", "") or ""),
            manufacturer=str(getattr(p, "manufacturer", "") or ""),
            kind=classify_serial_port(p.device, getattr(p, "description", ""),
                                      getattr(p, "hwid", ""), vid),
        ))
    puertos.sort(key=lambda p: (p.hidden, _numero_com(p.device), p.device))
    return puertos


def _numero_com(device):
    m = re.search(r"(\d+)$", device)
    return int(m.group(1)) if m else 0


# -- setupapi (Windows) -------------------------------------------------------------

DIGCF_PRESENT = 0x2
DIGCF_ALLCLASSES = 0x4
DIGCF_DEVICEINTERFACE = 0x10
SPDRP_DEVICEDESC = 0x0
SPDRP_HARDWAREID = 0x1
SPDRP_COMPATIBLEIDS = 0x2
SPDRP_SERVICE = 0x4
ERROR_NO_MORE_ITEMS = 259
ERROR_INSUFFICIENT_BUFFER = 122
KEY_READ = 0x20019
DN_HAS_PROBLEM = 0x400
CR_SUCCESS = 0


def _structs():
    import ctypes
    from ctypes import Structure, c_uint8, c_uint16, c_uint32, c_void_p

    class GUID(Structure):
        _fields_ = [("Data1", c_uint32), ("Data2", c_uint16), ("Data3", c_uint16),
                    ("Data4", c_uint8 * 8)]

    class SP_DEVICE_INTERFACE_DATA(Structure):
        _fields_ = [("cbSize", c_uint32), ("InterfaceClassGuid", GUID),
                    ("Flags", c_uint32), ("Reserved", c_void_p)]

    class SP_DEVINFO_DATA(Structure):
        _fields_ = [("cbSize", c_uint32), ("ClassGuid", GUID),
                    ("DevInst", c_uint32), ("Reserved", c_void_p)]

    class DEVPROPKEY(Structure):
        _fields_ = [("fmtid", GUID), ("pid", c_uint32)]

    return ctypes, GUID, SP_DEVICE_INTERFACE_DATA, SP_DEVINFO_DATA, DEVPROPKEY


def guid_from_string(texto, GUID):
    import uuid
    u = uuid.UUID(texto)
    g = GUID()
    g.Data1, g.Data2, g.Data3 = u.fields[0], u.fields[1], u.fields[2]
    for i, b in enumerate(u.bytes[8:]):
        g.Data4[i] = b
    return g


# DEVPKEY_Device_BusReportedDeviceDesc: la descripción que da el propio USB.
_DEVPKEY_BUS_REPORTED = ("{540b947e-8b40-45bc-a8a2-6a0b894cbda2}", 4)


def _setupapi_real():
    import ctypes
    from ctypes import c_int, c_uint32, c_void_p, c_wchar_p

    api = ctypes.WinDLL("setupapi", use_last_error=True)
    api.SetupDiGetClassDevsW.restype = c_void_p
    api.SetupDiGetClassDevsW.argtypes = [c_void_p, c_wchar_p, c_void_p, c_uint32]
    api.SetupDiEnumDeviceInterfaces.argtypes = [c_void_p, c_void_p, c_void_p, c_uint32, c_void_p]
    api.SetupDiEnumDeviceInterfaces.restype = c_int
    api.SetupDiGetDeviceInterfaceDetailW.argtypes = [c_void_p, c_void_p, c_void_p, c_uint32,
                                                     c_void_p, c_void_p]
    api.SetupDiGetDeviceInterfaceDetailW.restype = c_int
    api.SetupDiEnumDeviceInfo.argtypes = [c_void_p, c_uint32, c_void_p]
    api.SetupDiEnumDeviceInfo.restype = c_int
    api.SetupDiGetDeviceRegistryPropertyW.argtypes = [c_void_p, c_void_p, c_uint32, c_void_p,
                                                      c_void_p, c_uint32, c_void_p]
    api.SetupDiGetDeviceRegistryPropertyW.restype = c_int
    api.SetupDiGetDevicePropertyW.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p,
                                              c_uint32, c_void_p, c_uint32]
    api.SetupDiGetDevicePropertyW.restype = c_int
    api.SetupDiOpenDeviceInterfaceRegKey.argtypes = [c_void_p, c_void_p, c_uint32, c_uint32]
    api.SetupDiOpenDeviceInterfaceRegKey.restype = c_void_p
    api.SetupDiDestroyDeviceInfoList.argtypes = [c_void_p]
    api.SetupDiDestroyDeviceInfoList.restype = c_int
    api.last_error = ctypes.get_last_error
    return api


def _cfgmgr_real():
    import ctypes
    from ctypes import c_uint32, c_void_p

    api = ctypes.WinDLL("cfgmgr32")
    api.CM_Get_DevNode_Status.argtypes = [c_void_p, c_void_p, c_uint32, c_uint32]
    api.CM_Get_DevNode_Status.restype = c_uint32
    return api


def _utf16(ctypes, buffer, offset=0):
    """Texto UTF-16 de un buffer (también en Linux, donde wchar mide 4 bytes)."""
    crudo = bytes(buffer)[offset:]
    fin = 0
    while fin + 1 < len(crudo) and crudo[fin:fin + 2] != b"\x00\x00":
        fin += 2
    return crudo[:fin].decode("utf-16-le", errors="replace")


def _multi_sz(crudo):
    return [p for p in bytes(crudo).decode("utf-16-le", errors="replace").split("\x00") if p]


def _handle_valido(h):
    return bool(h) and h not in (-1, (1 << 64) - 1, (1 << 32) - 1)


def _propiedad_registro(api, ct, hdev, devinfo, prop):
    """Bytes de una propiedad SPDRP_*, o b"" si no está."""
    requerido = ct.c_uint32(0)
    tipo = ct.c_uint32(0)
    api.SetupDiGetDeviceRegistryPropertyW(hdev, ct.byref(devinfo), prop, ct.byref(tipo),
                                          None, 0, ct.byref(requerido))
    if not requerido.value:
        return b""
    buffer = ct.create_string_buffer(requerido.value)
    if not api.SetupDiGetDeviceRegistryPropertyW(hdev, ct.byref(devinfo), prop, ct.byref(tipo),
                                                 buffer, requerido.value, ct.byref(requerido)):
        return b""
    return buffer.raw[:requerido.value]


def _descripcion_bus(api, ct, hdev, devinfo, DEVPROPKEY, GUID):
    clave = DEVPROPKEY(guid_from_string(_DEVPKEY_BUS_REPORTED[0], GUID), _DEVPKEY_BUS_REPORTED[1])
    tipo = ct.c_uint32(0)
    requerido = ct.c_uint32(0)
    buffer = ct.create_string_buffer(512)
    if api.SetupDiGetDevicePropertyW(hdev, ct.byref(devinfo), ct.byref(clave), ct.byref(tipo),
                                     buffer, 512, ct.byref(requerido), 0):
        return _utf16(ct, buffer.raw[:requerido.value])
    return ""


def _puerto_usb(api, ct, hdev, ifdata, winreg=None):
    """ "USB001" desde la clave de registro de la interfaz, o "". """
    if winreg is None:
        import winreg
    hkey = api.SetupDiOpenDeviceInterfaceRegKey(hdev, ct.byref(ifdata), 0, KEY_READ)
    if not _handle_valido(hkey):
        return ""
    try:
        numero, _ = winreg.QueryValueEx(hkey, "Port Number")
        try:
            base, _ = winreg.QueryValueEx(hkey, "Base Name")
        except OSError:
            base = "USB"
        return f"{base}{int(numero):03d}"
    except OSError:
        return ""
    finally:
        try:
            winreg.CloseKey(hkey)
        except Exception:
            pass


def windows_usbprint_interfaces(setupapi=None, winreg=None):
    """
    [(ruta, puerto, descripción del bus)] de las interfaces usbprint presentes.
    """
    ct, GUID, SP_DEVICE_INTERFACE_DATA, SP_DEVINFO_DATA, DEVPROPKEY = _structs()
    api = setupapi or _setupapi_real()
    guid = guid_from_string(GUID_DEVINTERFACE_USBPRINT, GUID)
    hdev = api.SetupDiGetClassDevsW(ct.byref(guid), None, None,
                                    DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if not _handle_valido(hdev):
        raise OSError(api.last_error(), "SetupDiGetClassDevs falló")
    resultado = []
    try:
        indice = 0
        while True:
            ifdata = SP_DEVICE_INTERFACE_DATA()
            ifdata.cbSize = ct.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not api.SetupDiEnumDeviceInterfaces(hdev, None, ct.byref(guid), indice,
                                                   ct.byref(ifdata)):
                break  # ERROR_NO_MORE_ITEMS
            indice += 1
            requerido = ct.c_uint32(0)
            api.SetupDiGetDeviceInterfaceDetailW(hdev, ct.byref(ifdata), None, 0,
                                                 ct.byref(requerido), None)
            if requerido.value < 6:
                continue
            detalle = ct.create_string_buffer(requerido.value + 2)
            # cbSize del struct fijo: 8 en 64 bits (DWORD + WCHAR con relleno), 6 en 32.
            ct.c_uint32.from_buffer(detalle).value = 8 if ct.sizeof(ct.c_void_p) == 8 else 6
            devinfo = SP_DEVINFO_DATA()
            devinfo.cbSize = ct.sizeof(SP_DEVINFO_DATA)
            if not api.SetupDiGetDeviceInterfaceDetailW(hdev, ct.byref(ifdata), detalle,
                                                        requerido.value, None, ct.byref(devinfo)):
                continue
            ruta = _utf16(ct, detalle.raw, 4)
            try:
                puerto = _puerto_usb(api, ct, hdev, ifdata, winreg)
            except Exception as e:
                logger.debug(f"Sin puerto USB00x para {ruta}: {e}")
                puerto = ""
            try:
                descripcion = _descripcion_bus(api, ct, hdev, devinfo, DEVPROPKEY, GUID)
            except Exception:
                descripcion = ""
            resultado.append((ruta, puerto, descripcion))
    finally:
        api.SetupDiDestroyDeviceInfoList(hdev)
    return resultado


def windows_usb_devices(setupapi=None, cfgmgr=None):
    """
    Todos los dispositivos USB presentes: [{hardware_ids, compatible_ids,
    service, description, problem}]. Para detectar impresoras que Windows no
    reconoce o que tienen WinUSB.
    """
    ct, GUID, _ifdata, SP_DEVINFO_DATA, _k = _structs()
    api = setupapi or _setupapi_real()
    cm = cfgmgr if cfgmgr is not None else _cfgmgr_real()
    hdev = api.SetupDiGetClassDevsW(None, "USB", None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if not _handle_valido(hdev):
        raise OSError(api.last_error(), "SetupDiGetClassDevs(USB) falló")
    dispositivos = []
    try:
        indice = 0
        while True:
            devinfo = SP_DEVINFO_DATA()
            devinfo.cbSize = ct.sizeof(SP_DEVINFO_DATA)
            if not api.SetupDiEnumDeviceInfo(hdev, indice, ct.byref(devinfo)):
                break
            indice += 1
            estado, problema = ct.c_uint32(0), ct.c_uint32(0)
            tiene_problema = False
            if cm.CM_Get_DevNode_Status(ct.byref(estado), ct.byref(problema), devinfo.DevInst,
                                        0) == CR_SUCCESS:
                tiene_problema = bool(estado.value & DN_HAS_PROBLEM)
            dispositivos.append({
                "hardware_ids": _multi_sz(_propiedad_registro(api, ct, hdev, devinfo, SPDRP_HARDWAREID)),
                "compatible_ids": _multi_sz(_propiedad_registro(api, ct, hdev, devinfo, SPDRP_COMPATIBLEIDS)),
                "service": _utf16(ct, _propiedad_registro(api, ct, hdev, devinfo, SPDRP_SERVICE)),
                "description": _utf16(ct, _propiedad_registro(api, ct, hdev, devinfo, SPDRP_DEVICEDESC)),
                "problem": problema.value if tiene_problema else 0,
            })
    finally:
        api.SetupDiDestroyDeviceInfoList(hdev)
    return dispositivos


def read_device_id(path, kernel32=None):
    """Device ID IEEE 1284 por IOCTL (un segundo como mucho). {} si no se pudo."""
    from fiscalberry.common.usbprint_driver import (
        IOCTL_USBPRINT_GET_1284_ID, Win32File, parse_1284_id)
    try:
        archivo = Win32File(path, kernel32)
    except OSError as e:
        logger.debug(f"No se pudo abrir {path} para leer el modelo: {e}")
        return {}
    try:
        return parse_1284_id(archivo.ioctl(IOCTL_USBPRINT_GET_1284_ID, 1024, timeout=1.0))
    except (OSError, TimeoutError) as e:
        logger.debug(f"Sin Device ID en {path}: {e}")
        return {}
    finally:
        archivo.close()


def list_usbprint_devices(interfaces=None, device_id=read_device_id, with_details=True,
                          platform=None):
    """
    Impresoras USB por usbprint. `with_details` lee además el modelo (abre el
    dispositivo un instante); el driver no lo necesita para imprimir.
    """
    platform = sys.platform if platform is None else platform
    if interfaces is None:
        if platform != "win32":
            return []
        interfaces = windows_usbprint_interfaces
    dispositivos = []
    vistos = set()
    for ruta, puerto, descripcion in interfaces():
        ids = parse_device_path(ruta)
        if ids is None or ruta.lower() in vistos:
            continue
        vistos.add(ruta.lower())
        vid, pid, serie = ids
        detalles = device_id(ruta) if with_details and device_id else {}
        dispositivos.append(UsbPrintDevice(ruta, vid, pid, serie, puerto, descripcion,
                                           detalles or {}))
    dispositivos.sort(key=lambda d: (d.port_name or "~", d.device_path.lower()))
    return dispositivos


# -- Incompatibles -----------------------------------------------------------------

INCOMPATIBLE_NO_DRIVER = "sin_driver"
INCOMPATIBLE_WINUSB = "winusb"

_WINUSB_SERVICES = {"winusb", "libusbk", "libusb0", "libusb-win32"}
_USB_ID = re.compile(r"USB\\VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", re.I)


@dataclass(frozen=True)
class IncompatibleUsb:
    vendor_id: int
    product_id: int
    reason: str
    description: str = ""
    service: str = ""

    @property
    def title(self):
        marca = USB_VENDORS.get(self.vendor_id)
        return f"Impresora USB {marca}" if marca else (self.description or "Impresora USB")

    @property
    def ids(self):
        return f"{self.vendor_id:04X}:{self.product_id:04X}"


def find_incompatible_usb(devices, known=(), vendors=USB_VENDORS):
    """
    Impresoras USB que Fiscalberry no puede usar sin cambiar drivers.

    Se consideran impresora: clase USB 07 (compatible IDs) o un VID de una
    marca de impresoras conocida. `known` son los (vid, pid) que ya se
    encontraron por usbprint o COM, que no se repiten.
    """
    conocidos = set(known)
    incompatibles = []
    for d in devices:
        ids = next((m for m in (_USB_ID.search(h) for h in d.get("hardware_ids", ())) if m), None)
        if ids is None:
            continue
        vid, pid = int(ids.group(1), 16), int(ids.group(2), 16)
        if (vid, pid) in conocidos:
            continue
        compatibles = " ".join(d.get("compatible_ids", ())).upper()
        es_impresora = "CLASS_07" in compatibles or vid in vendors
        if not es_impresora:
            continue
        servicio = str(d.get("service", "")).strip()
        if servicio.lower() in _WINUSB_SERVICES:
            razon = INCOMPATIBLE_WINUSB
        elif not servicio or d.get("problem"):
            razon = INCOMPATIBLE_NO_DRIVER
        else:
            continue  # tiene su driver (usbprint, usbser, el del fabricante)
        conocidos.add((vid, pid))
        incompatibles.append(IncompatibleUsb(vid, pid, razon, str(d.get("description", "")),
                                             servicio))
    return incompatibles


# -- Búsqueda completa ---------------------------------------------------------------

@dataclass
class UsbSearchResult:
    usbprint: list = field(default_factory=list)
    serial: list = field(default_factory=list)
    incompatible: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def search_usb(platform=None, usbprint=None, serial=None, usb_devices=None):
    """usbprint + COM + incompatibles. No lanza: cada error queda anotado."""
    platform = sys.platform if platform is None else platform
    resultado = UsbSearchResult()
    try:
        resultado.usbprint = usbprint() if usbprint else list_usbprint_devices(platform=platform)
    except Exception as e:
        logger.warning(f"No se pudieron listar las impresoras USB: {e}")
        resultado.errors.append("No se pudieron revisar las impresoras USB.")
    try:
        resultado.serial = serial() if serial else list_serial_ports()
    except Exception as e:
        logger.warning(f"No se pudieron listar los puertos COM: {e}")
        resultado.errors.append("No se pudieron revisar los puertos COM.")
    if usb_devices is not None or platform == "win32":
        try:
            dispositivos = (usb_devices or windows_usb_devices)()
            conocidos = {(d.vendor_id, d.product_id) for d in resultado.usbprint}
            conocidos |= {(p.vendor_id, p.product_id) for p in resultado.serial
                          if p.vendor_id is not None}
            resultado.incompatible = find_incompatible_usb(dispositivos, conocidos)
        except Exception as e:
            logger.debug(f"No se pudieron revisar los dispositivos USB: {e}")
    return resultado
