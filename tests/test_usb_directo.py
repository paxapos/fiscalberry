# coding=utf-8
"""
USB directo en Windows (#183): usbprint (escenario 2) y COM (escenario 3).

Sin Windows ni impresoras: setupapi, cfgmgr32, el registro y kernel32 son
falsos, pero los structs y buffers son los de verdad (ctypes). La impresora
USB simulada contesta DLE EOT como una térmica real, se puede "desenchufar"
en medio de la prueba y "ocupar" como si el spooler estuviera imprimiendo.
"""

import ctypes
import sys
from types import SimpleNamespace

import pytest

from fiscalberry.common import usb_discovery as ud
from fiscalberry.common import usbprint_driver as up
from fiscalberry.common.printer_setup import PrinterCandidate, TRANSPORT_USBPRINT

GUID_TXT = "{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"
RUTA_EPSON = r"\\?\usb#vid_04b8&pid_0e15#5839504b3031373431#" + GUID_TXT
RUTA_SIN_SERIE = r"\\?\usb#vid_0fe6&pid_811e#6&2c5b3a7&0&1#" + GUID_TXT
RUTA_SIN_SERIE_2 = r"\\?\usb#vid_0fe6&pid_811e#6&2c5b3a7&0&2#" + GUID_TXT
RUTA_COMPUESTA = r"\\?\usb#vid_0519&pid_0003&mi_00#7&1a2b3c4d&0&0000#" + GUID_TXT


# ---------------------------------------------------------------------------
# Identidad desde la ruta del dispositivo
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ruta,esperado", [
    (RUTA_EPSON, (0x04B8, 0x0E15, "5839504b3031373431")),
    (RUTA_SIN_SERIE, (0x0FE6, 0x811E, "")),
    (RUTA_COMPUESTA, (0x0519, 0x0003, "")),
    (RUTA_EPSON.upper(), (0x04B8, 0x0E15, "5839504B3031373431")),
    (r"\\?\hid#vid_046d&pid_c077#abc", None),
    ("", None),
])
def test_identidad_desde_la_ruta(ruta, esperado):
    assert ud.parse_device_path(ruta) == esperado


def test_la_identidad_guardada_es_vid_pid_serie_no_la_ruta():
    d = ud.UsbPrintDevice(RUTA_EPSON, 0x04B8, 0x0E15, "5839504b3031373431", "USB001",
                          ieee1284={"MFG": "EPSON", "MDL": "TM-T20II"})
    c = d.candidate()
    assert c.transport == TRANSPORT_USBPRINT
    assert c.display_name == "EPSON TM-T20II"
    assert c.stable_id == "usbprint:04b8:0e15:5839504b3031373431"
    guardado = c.config_to_persist()
    assert "device_path" not in guardado
    assert guardado["serial_number"] == "5839504b3031373431"
    # Para la prueba sí se usa la ruta.
    assert c.driver_config["device_path"] == RUTA_EPSON


def test_sin_serie_la_ruta_es_parte_de_la_identidad():
    a = ud.UsbPrintDevice(RUTA_SIN_SERIE, 0x0FE6, 0x811E).candidate()
    b = ud.UsbPrintDevice(RUTA_SIN_SERIE_2, 0x0FE6, 0x811E).candidate()
    assert a.stable_id != b.stable_id  # dos térmicas iguales sin serie
    assert a.config_to_persist()["device_path"] == RUTA_SIN_SERIE


@pytest.mark.parametrize("dispositivo,titulo", [
    (ud.UsbPrintDevice(RUTA_EPSON, 0x04B8, 0x0E15, ieee1284={"MFG": "EPSON", "MDL": "TM-T88V"}),
     "EPSON TM-T88V"),
    (ud.UsbPrintDevice(RUTA_EPSON, 0x04B8, 0x0E15, bus_description="TM-T20II"), "TM-T20II"),
    (ud.UsbPrintDevice(RUTA_EPSON, 0x04B8, 0x0E15), "Impresora USB Epson"),
    (ud.UsbPrintDevice(RUTA_SIN_SERIE, 0x0FE6, 0x811E), "Impresora USB"),
])
def test_nombre_para_mostrar(dispositivo, titulo):
    assert dispositivo.title == titulo


def test_device_id_ieee_1284():
    texto = b"MFG:EPSON;CMD:ESC/POS;MDL:TM-T20II;CLS:PRINTER;DES:EPSON TM-T20II Receipt;"
    respuesta = (len(texto) + 2).to_bytes(2, "big") + texto + b"\x00" * 10
    campos = up.parse_1284_id(respuesta)
    assert campos["MFG"] == "EPSON" and campos["MDL"] == "TM-T20II"
    assert up.model_from_1284(campos) == "EPSON TM-T20II"
    largo = b"MANUFACTURER:Star;MODEL:TSP100;"
    assert up.model_from_1284(up.parse_1284_id(b"\x00\x21" + largo)) == "Star TSP100"
    assert up.model_from_1284(up.parse_1284_id(b"")) == ""
    assert up.model_from_1284({"MFG": "EPSON", "MDL": "EPSON TM-T20"}) == "EPSON TM-T20"


def test_estado_lpt_es_informativo():
    assert up.parse_lpt_status(0x18) == {"sin_papel": False, "seleccionada": True, "error": False}
    assert up.parse_lpt_status(0x20) == {"sin_papel": True, "seleccionada": False, "error": True}
    assert up.parse_lpt_status(None) == {}


# ---------------------------------------------------------------------------
# setupapi simulado
# ---------------------------------------------------------------------------

def _escribir_utf16(buffer, texto, offset=0):
    datos = (texto + "\0").encode("utf-16-le")
    ctypes.memmove(ctypes.addressof(buffer) + offset, datos, len(datos))
    return len(datos)


class SetupApiFalsa:
    """Interfaces usbprint y dispositivos USB como los devolvería Windows."""

    HDEV = 0x5000

    def __init__(self, interfaces=(), dispositivos=()):
        self.interfaces = list(interfaces)      # [(ruta, puerto, desc_bus)]
        self.dispositivos = list(dispositivos)  # [dict]
        self.destruidos = 0
        self.claves = {}

    def last_error(self):
        return 259

    def SetupDiGetClassDevsW(self, guid, enumerador, hwnd, flags):
        if flags & ud.DIGCF_DEVICEINTERFACE:
            g = guid._obj
            assert (g.Data1, g.Data2, g.Data3) == (0x28D78FAD, 0x5A12, 0x11D1)
            assert flags & ud.DIGCF_PRESENT
        else:
            assert enumerador == "USB" and flags & ud.DIGCF_ALLCLASSES
        return self.HDEV

    def SetupDiEnumDeviceInterfaces(self, hdev, devinfo, guid, indice, ifdata):
        assert ifdata._obj.cbSize == ctypes.sizeof(ifdata._obj)
        if indice >= len(self.interfaces):
            return 0
        ifdata._obj.Reserved = indice + 1  # para saber cuál es después
        return 1

    def SetupDiGetDeviceInterfaceDetailW(self, hdev, ifdata, detalle, tam, requerido, devinfo):
        ruta = self.interfaces[ifdata._obj.Reserved - 1][0]
        necesario = 4 + (len(ruta) + 1) * 2
        if detalle is None:
            requerido._obj.value = necesario
            return 0
        assert ctypes.c_uint32.from_buffer(detalle).value in (6, 8)  # cbSize fijo
        assert tam >= necesario
        _escribir_utf16(detalle, ruta, 4)
        devinfo._obj.DevInst = ifdata._obj.Reserved
        return 1

    def SetupDiOpenDeviceInterfaceRegKey(self, hdev, ifdata, reservado, acceso):
        puerto = self.interfaces[ifdata._obj.Reserved - 1][1]
        if not puerto:
            return (1 << 64) - 1  # INVALID_HANDLE_VALUE
        clave = 0x9000 + ifdata._obj.Reserved
        self.claves[clave] = puerto
        return clave

    def SetupDiGetDevicePropertyW(self, hdev, devinfo, clave, tipo, buffer, tam, requerido, flags):
        assert clave._obj.pid == 4  # DEVPKEY_Device_BusReportedDeviceDesc
        desc = self.interfaces[devinfo._obj.DevInst - 1][2]
        if not desc:
            return 0
        requerido._obj.value = _escribir_utf16(buffer, desc)
        return 1

    def SetupDiEnumDeviceInfo(self, hdev, indice, devinfo):
        if indice >= len(self.dispositivos):
            return 0
        devinfo._obj.DevInst = indice + 1
        return 1

    def SetupDiGetDeviceRegistryPropertyW(self, hdev, devinfo, prop, tipo, buffer, tam, requerido):
        d = self.dispositivos[devinfo._obj.DevInst - 1]
        valor = {ud.SPDRP_HARDWAREID: d.get("hardware_ids"),
                 ud.SPDRP_COMPATIBLEIDS: d.get("compatible_ids"),
                 ud.SPDRP_SERVICE: d.get("service"),
                 ud.SPDRP_DEVICEDESC: d.get("description")}[prop]
        if not valor:
            requerido._obj.value = 0
            return 0
        texto = "\0".join(valor) + "\0" if isinstance(valor, list) else valor
        datos = (texto + "\0").encode("utf-16-le")
        if buffer is None:
            requerido._obj.value = len(datos)
            return 0
        ctypes.memmove(buffer, datos, len(datos))
        requerido._obj.value = len(datos)
        return 1

    def SetupDiDestroyDeviceInfoList(self, hdev):
        self.destruidos += 1
        return 1


class WinregFalso:
    def __init__(self, api):
        self.api = api
        self.cerradas = []

    def QueryValueEx(self, clave, nombre):
        puerto = self.api.claves[clave]
        if nombre == "Port Number":
            return int(puerto[3:]), 4
        if nombre == "Base Name":
            return puerto[:3], 1
        raise OSError(2, "no existe")

    def CloseKey(self, clave):
        self.cerradas.append(clave)


class CfgMgrFalso:
    def __init__(self, api):
        self.api = api

    def CM_Get_DevNode_Status(self, estado, problema, devinst, flags):
        d = self.api.dispositivos[devinst - 1]
        if d.get("problem"):
            estado._obj.value = ud.DN_HAS_PROBLEM
            problema._obj.value = d["problem"]
        return ud.CR_SUCCESS


def test_enumeracion_de_interfaces_usbprint():
    api = SetupApiFalsa(interfaces=[
        (RUTA_EPSON, "USB001", "TM-T20II"),
        (RUTA_SIN_SERIE, "USB002", ""),
        (RUTA_COMPUESTA, "", "TSP143"),
    ])
    reg = WinregFalso(api)
    interfaces = ud.windows_usbprint_interfaces(api, reg)

    assert interfaces == [(RUTA_EPSON, "USB001", "TM-T20II"),
                          (RUTA_SIN_SERIE, "USB002", ""),
                          (RUTA_COMPUESTA, "", "TSP143")]
    assert api.destruidos == 1          # la lista de SetupDi se libera
    assert len(reg.cerradas) == 2       # y cada clave de registro abierta


def test_sin_impresoras_usb():
    api = SetupApiFalsa()
    assert ud.windows_usbprint_interfaces(api, WinregFalso(api)) == []
    assert api.destruidos == 1


def test_lista_de_impresoras_usbprint():
    interfaces = [(RUTA_SIN_SERIE, "USB002", ""), (RUTA_EPSON, "USB001", "TM-T20II"),
                  (RUTA_EPSON, "USB001", "TM-T20II"),            # duplicada
                  (r"\\?\raro#sin-ids#{x}", "", "")]              # ruta que no es USB
    modelos = {RUTA_EPSON: {"MFG": "EPSON", "MDL": "TM-T20II"}}
    dispositivos = ud.list_usbprint_devices(lambda: interfaces, device_id=modelos.get)

    assert [d.port_name for d in dispositivos] == ["USB001", "USB002"]
    assert dispositivos[0].title == "EPSON TM-T20II"
    assert dispositivos[1].serial == ""


def test_fuera_de_windows_no_hay_usbprint():
    assert ud.list_usbprint_devices(platform="linux") == []


def test_dispositivos_usb_para_detectar_incompatibles():
    api = SetupApiFalsa(dispositivos=[
        {"hardware_ids": ["USB\\VID_04B8&PID_0202&REV_0100", "USB\\VID_04B8&PID_0202"],
         "compatible_ids": ["USB\\Class_ff&SubClass_00", "USB\\Class_ff"],
         "service": "", "description": "Dispositivo desconocido", "problem": 28},
        {"hardware_ids": ["USB\\VID_046D&PID_C077"], "compatible_ids": ["USB\\Class_03"],
         "service": "HidUsb", "description": "Mouse"},
    ])
    dispositivos = ud.windows_usb_devices(api, CfgMgrFalso(api))
    assert dispositivos[0]["hardware_ids"][1] == "USB\\VID_04B8&PID_0202"
    assert dispositivos[0]["problem"] == 28 and dispositivos[0]["service"] == ""
    assert dispositivos[1]["service"] == "HidUsb" and dispositivos[1]["problem"] == 0
    assert api.destruidos == 1


# ---------------------------------------------------------------------------
# Drivers incompatibles: nunca se modifican
# ---------------------------------------------------------------------------

def usb(vid, pid, servicio="", clase="ff", problema=0, desc=""):
    return {"hardware_ids": [f"USB\\VID_{vid:04X}&PID_{pid:04X}&REV_0100"],
            "compatible_ids": [f"USB\\Class_{clase}&SubClass_01", f"USB\\Class_{clase}"],
            "service": servicio, "problem": problema, "description": desc}


def test_impresoras_que_no_se_pueden_usar_sin_tocar_drivers():
    dispositivos = [
        usb(0x04B8, 0x0202, "", problema=28, desc="Dispositivo desconocido"),  # Epson sin driver
        usb(0x0FE6, 0x811E, "WinUSB", clase="07"),     # clase impresora pasada a WinUSB (Zadig)
        usb(0x0519, 0x0003, "usbprint", clase="07"),   # bien: la ve usbprint
        usb(0x04B8, 0x0E15, "usbccgp"),                # compuesto: su interfaz tiene driver
        usb(0x046D, 0xC077, "", clase="03"),           # un mouse sin driver: no es impresora
        usb(0x1504, 0x0006, "", problema=28),          # Bixolon ya encontrada por usbprint
    ]
    incompatibles = ud.find_incompatible_usb(dispositivos, known={(0x1504, 0x0006)})

    assert [(i.vendor_id, i.reason) for i in incompatibles] == [
        (0x04B8, ud.INCOMPATIBLE_NO_DRIVER), (0x0FE6, ud.INCOMPATIBLE_WINUSB)]
    assert incompatibles[0].title == "Impresora USB Epson"
    assert incompatibles[1].service == "WinUSB"


# ---------------------------------------------------------------------------
# Puertos COM (escenario 3)
# ---------------------------------------------------------------------------

def puerto(device, description, hwid, vid=None, pid=None, serial_number=None):
    return SimpleNamespace(device=device, description=description, hwid=hwid, vid=vid, pid=pid,
                           serial_number=serial_number, manufacturer="")


SALIDA_COMPORTS = [
    puerto("COM5", "Standard Serial over Bluetooth link (COM5)",
           "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000\\7&1234&0&000000000000_00000000"),
    puerto("COM1", "Puerto de comunicaciones (COM1)", "ACPI\\PNP0501\\0"),
    puerto("COM12", "USB-SERIAL CH340 (COM12)", "USB VID:PID=1A86:7523 SER= LOCATION=1-4",
           0x1A86, 0x7523),
    puerto("COM3", "Dispositivo serie USB (COM3)", "USB VID:PID=04B8:0E28 SER=X4TK001234",
           0x04B8, 0x0E28, "X4TK001234"),
    puerto("COM7", "Conexant USB Modem (COM7)", "USB\\VID_0572&PID_1340"),
]


def test_puertos_com_clasificados_y_ordenados():
    puertos = ud.list_serial_ports(lambda: SALIDA_COMPORTS)
    por_com = {p.device: p for p in puertos}

    assert [p.device for p in puertos if not p.hidden] == ["COM3", "COM12"]
    assert por_com["COM5"].kind == "bluetooth" and not por_com["COM5"].selectable
    assert por_com["COM1"].kind == "placa" and por_com["COM1"].hidden
    assert por_com["COM7"].kind == "modem"
    assert por_com["COM12"].chip == "CH340"
    assert por_com["COM3"].title == "Impresora USB Epson (COM3)"
    assert por_com["COM12"].title == "Impresora USB (COM12)"


def test_la_identidad_de_un_com_usb_sobrevive_al_cambio_de_numero():
    c = ud.list_serial_ports(lambda: SALIDA_COMPORTS[3:4])[0].candidate()
    assert c.stable_id == "serial:04b8:0e28:X4TK001234"
    assert c.driver_config["devfile"] == "COM3"
    assert c.driver_config["_usb_serial"] == "X4TK001234"
    assert c.display_name == "Impresora USB Epson (COM3)"


def test_busqueda_usb_no_revienta_si_falla_una_parte():
    def roto():
        raise OSError(5, "acceso denegado")

    r = ud.search_usb(platform="win32", usbprint=roto, serial=lambda: [],
                      usb_devices=lambda: [usb(0x04B8, 0x0202, "", problema=28)])
    assert r.errors == ["No se pudieron revisar las impresoras USB."]
    assert len(r.incompatible) == 1

    r = ud.search_usb(platform="linux", usbprint=lambda: [], serial=roto)
    assert r.errors == ["No se pudieron revisar los puertos COM."]
    assert r.incompatible == []


# ---------------------------------------------------------------------------
# kernel32 falso: la impresora USB simulada
# ---------------------------------------------------------------------------

class ImpresoraUsbFalsa:
    """Una térmica por usbprint: acumula bytes y contesta DLE EOT."""

    def __init__(self, estado=(0x16, 0x12, 0x12), sin_endpoint_in=False, lpt=0x18):
        self.recibido = bytearray()
        self.estado = {1: estado[0], 2: estado[1], 4: estado[2]}
        self.pendiente = b""
        self.sin_endpoint_in = sin_endpoint_in
        self.lpt = lpt
        self.conectada = True

    def write(self, datos):
        if not self.conectada:
            raise up.WindowsIOError(up.ERROR_DEVICE_NOT_CONNECTED, "desenchufada")
        self.recibido += datos
        if datos[:2] == b"\x10\x04" and len(datos) >= 3:
            self.pendiente += bytes([self.estado[datos[2]]])

    def read(self):
        respuesta, self.pendiente = self.pendiente, b""
        return respuesta


class Kernel32Falso:
    """CreateFile/WriteFile/ReadFile/DeviceIoControl con E/S superpuesta."""

    def __init__(self, dispositivos, ocupada=0, modo="inmediato"):
        self.dispositivos = dispositivos    # {ruta: ImpresoraUsbFalsa}
        self.ocupada = ocupada              # cuántos CreateFile fallan por "en uso"
        self.modo = modo                    # inmediato, pendiente, colgado
        self.handles = {}
        self.error = 0
        self.eventos = 0
        self.cancelados = 0
        self.abiertos = 0
        self._siguiente = 100
        self._pendiente = None

    def last_error(self):
        return self.error

    def CreateFileW(self, ruta, acceso, compartir, seg, disp, flags, plantilla):
        assert flags & up.FILE_FLAG_OVERLAPPED
        assert acceso == up.GENERIC_READ | up.GENERIC_WRITE
        if self.ocupada:
            self.ocupada -= 1
            self.error = up.ERROR_SHARING_VIOLATION
            return up.INVALID_HANDLE_VALUE
        dispositivo = self.dispositivos.get(ruta)
        if dispositivo is None or not dispositivo.conectada:
            self.error = up.ERROR_FILE_NOT_FOUND
            return up.INVALID_HANDLE_VALUE
        self._siguiente += 1
        self.handles[self._siguiente] = dispositivo
        self.abiertos += 1
        return self._siguiente

    def CreateEventW(self, *a):
        self.eventos += 1
        return 7000 + self.eventos

    def CloseHandle(self, h):
        if h in self.handles:
            del self.handles[h]
            self.abiertos -= 1
        elif h > 7000:
            self.eventos -= 1
        return 1

    def _terminar(self, transferidos, n, error=None):
        if self.modo == "inmediato":
            if error:
                self.error = error
                return 0
            transferidos._obj.value = n
            return 1
        self._pendiente = (n, error)
        self.error = up.ERROR_IO_PENDING
        return 0

    def WriteFile(self, h, buffer, n, transferidos, ov):
        try:
            self.handles[h].write(bytes(buffer)[:n])
        except up.WindowsIOError as e:
            return self._terminar(transferidos, 0, e.winerror)
        return self._terminar(transferidos, n)

    def ReadFile(self, h, buffer, n, transferidos, ov):
        dispositivo = self.handles[h]
        if dispositivo.sin_endpoint_in:
            return self._terminar(transferidos, 0, up.ERROR_INVALID_FUNCTION)
        datos = dispositivo.read()[:n]
        ctypes.memmove(buffer, datos, len(datos))
        return self._terminar(transferidos, len(datos))

    def DeviceIoControl(self, h, codigo, entrada, tam_entrada, salida, tam_salida, transferidos, ov):
        if codigo == up.IOCTL_USBPRINT_GET_LPT_STATUS:
            ctypes.memmove(salida, bytes([self.handles[h].lpt]), 1)
            return self._terminar(transferidos, 1)
        return self._terminar(transferidos, 0, up.ERROR_NOT_SUPPORTED)

    def WaitForSingleObject(self, evento, ms):
        return up.WAIT_TIMEOUT if self.modo == "colgado" else up.WAIT_OBJECT_0

    def GetOverlappedResult(self, h, ov, transferidos, esperar):
        n, error = self._pendiente or (0, None)
        if self.modo == "colgado":
            self.error = up.ERROR_OPERATION_ABORTED
            return 0
        if error:
            self.error = error
            return 0
        transferidos._obj.value = n
        return 1

    def CancelIoEx(self, h, ov):
        self.cancelados += 1
        return 1


@pytest.mark.parametrize("modo", ["inmediato", "pendiente"])
def test_win32file_escribe_y_lee(modo):
    impresora = ImpresoraUsbFalsa()
    k32 = Kernel32Falso({RUTA_EPSON: impresora}, modo=modo)
    f = up.Win32File(RUTA_EPSON, k32)
    assert f.write(b"\x1b@hola") == 6
    f.write(b"\x10\x04\x01")
    assert f.read() == b"\x16"
    f.close()
    assert impresora.recibido == b"\x1b@hola\x10\x04\x01"
    assert k32.abiertos == 0 and k32.eventos == 0   # no quedan handles ni eventos


def test_una_escritura_colgada_se_cancela_por_timeout():
    k32 = Kernel32Falso({RUTA_EPSON: ImpresoraUsbFalsa()}, modo="colgado")
    f = up.Win32File(RUTA_EPSON, k32, write_timeout=0.5)
    with pytest.raises(TimeoutError):
        f.write(b"ticket")
    assert k32.cancelados == 1 and k32.eventos == 0
    f.close()


def test_abrir_una_ruta_que_no_existe():
    with pytest.raises(up.WindowsIOError) as e:
        up.Win32File(RUTA_EPSON, Kernel32Falso({}))
    assert e.value.winerror == up.ERROR_FILE_NOT_FOUND


# ---------------------------------------------------------------------------
# El driver UsbPrint
# ---------------------------------------------------------------------------

def dispositivo(ruta, serie=""):
    vid, pid, _ = ud.parse_device_path(ruta)
    return ud.UsbPrintDevice(ruta, vid, pid, serie)


def driver(k32, presentes, dormir=None, **config):
    return up.UsbPrint(kernel32=k32, enumerate_devices=lambda: presentes,
                       sleep=dormir or (lambda s: None), **config)


def test_con_serie_se_reencuentra_aunque_cambie_de_puerto():
    ruta_nueva = RUTA_EPSON.replace("#5839", "#5839")  # misma serie
    otra_ruta = r"\\?\usb#vid_04b8&pid_0e15#5839504b3031373431#{otro-puerto}"
    k32 = Kernel32Falso({otra_ruta: ImpresoraUsbFalsa()})
    d = driver(k32, [dispositivo(otra_ruta, "5839504b3031373431")],
               idVendor="0x04b8", idProduct="0x0e15", serial_number="5839504b3031373431",
               device_path=ruta_nueva)
    d._raw(b"hola")
    assert d.resolved_path == otra_ruta


def test_sin_serie_y_una_sola_igual_se_usa_aunque_cambie_la_ruta():
    k32 = Kernel32Falso({RUTA_SIN_SERIE_2: ImpresoraUsbFalsa()})
    d = driver(k32, [dispositivo(RUTA_SIN_SERIE_2)], idVendor=0x0FE6, idProduct=0x811E,
               device_path=RUTA_SIN_SERIE)
    assert d.resolve_path() == RUTA_SIN_SERIE_2


def test_dos_iguales_sin_serie_usa_la_ruta_guardada_o_avisa():
    presentes = [dispositivo(RUTA_SIN_SERIE), dispositivo(RUTA_SIN_SERIE_2)]
    d = driver(Kernel32Falso({}), presentes, idVendor=0x0FE6, idProduct=0x811E,
               device_path=RUTA_SIN_SERIE_2)
    assert d.resolve_path() == RUTA_SIN_SERIE_2

    d = driver(Kernel32Falso({}), presentes, idVendor=0x0FE6, idProduct=0x811E,
               device_path=r"\\?\usb#vid_0fe6&pid_811e#6&2c5b3a7&0&9#{x}")
    with pytest.raises(up.UsbPrintNotFound, match="varias"):
        d.resolve_path()


def test_desconectada_no_se_encuentra():
    d = driver(Kernel32Falso({}), [], idVendor=0x04B8, idProduct=0x0E15)
    with pytest.raises(up.UsbPrintNotFound) as e:
        d.open()
    assert e.value.winerror == up.ERROR_FILE_NOT_FOUND


def test_si_el_spooler_la_esta_usando_reintenta_con_backoff():
    esperas = []
    k32 = Kernel32Falso({RUTA_EPSON: ImpresoraUsbFalsa()}, ocupada=2)
    d = driver(k32, [dispositivo(RUTA_EPSON, "5839504b3031373431")], dormir=esperas.append,
               idVendor=0x04B8, idProduct=0x0E15, serial_number="5839504b3031373431")
    d._raw(b"x")
    assert esperas == [0.25, 0.5]


def test_si_sigue_ocupada_se_rinde_con_acceso_denegado():
    from fiscalberry.common.printer_test import PROBLEM_ACCESS_DENIED, classify_error

    k32 = Kernel32Falso({RUTA_EPSON: ImpresoraUsbFalsa()}, ocupada=99)
    d = driver(k32, [dispositivo(RUTA_EPSON)], idVendor=0x04B8, idProduct=0x0E15)
    with pytest.raises(up.WindowsIOError) as e:
        d.open()
    assert classify_error(e.value) == PROBLEM_ACCESS_DENIED


def test_cerrar_suelta_el_dispositivo_para_el_spooler():
    k32 = Kernel32Falso({RUTA_EPSON: ImpresoraUsbFalsa()})
    d = driver(k32, [dispositivo(RUTA_EPSON)], idVendor=0x04B8, idProduct=0x0E15)
    d._raw(b"x")
    assert k32.abiertos == 1
    d.close()
    d.close()  # idempotente
    assert k32.abiertos == 0


# ---------------------------------------------------------------------------
# La prueba de impresión por usbprint (escenario 2 de punta a punta)
# ---------------------------------------------------------------------------

def probar(impresora, k32=None, **kw):
    from fiscalberry.common.printer_test import PrintTestInfo, run_print_test

    k32 = k32 or Kernel32Falso({RUTA_EPSON: impresora})
    candidato = ud.UsbPrintDevice(RUTA_EPSON, 0x04B8, 0x0E15, "5839504b3031373431").candidate()
    presentes = [dispositivo(RUTA_EPSON, "5839504b3031373431")]

    def builder(config):
        d = up.UsbPrint(kernel32=k32, enumerate_devices=lambda: presentes,
                        sleep=lambda s: None, **{k: v for k, v in config.items()
                                                 if k != "driver"})
        return SimpleNamespace(driver=d)

    info = PrintTestInfo.for_candidate(candidato, commerce="Pizzeria", code="K7QX")
    return run_print_test(candidato, info, builder=builder, status_timeout=0.2, **kw), k32


def test_prueba_ok_con_estado_real():
    impresora = ImpresoraUsbFalsa()
    resultado, k32 = probar(impresora)
    assert resultado.technical_success
    assert resultado.status_before.online is True and resultado.status_after.known
    assert b"K7QX" in impresora.recibido
    assert resultado.lpt_status == {"sin_papel": False, "seleccionada": True, "error": False}
    assert k32.abiertos == 0  # cerró el dispositivo


def test_prueba_sin_papel_se_detecta_por_dle_eot():
    from fiscalberry.common.printer_test import PROBLEM_PAPER_OUT

    impresora = ImpresoraUsbFalsa(estado=(0x1E, 0x32, 0x72))  # fuera de línea, fin de papel
    resultado, _ = probar(impresora)
    assert not resultado.technical_success
    assert resultado.problem == PROBLEM_PAPER_OUT
    assert b"PRUEBA" not in impresora.recibido  # no se imprimió


def test_sin_endpoint_de_entrada_el_papel_decide():
    impresora = ImpresoraUsbFalsa(sin_endpoint_in=True)
    resultado, _ = probar(impresora)
    assert resultado.technical_success
    assert not resultado.status_before.known  # no contestó DLE EOT
    assert b"K7QX" in impresora.recibido


def test_desenchufada_en_medio_de_la_prueba():
    from fiscalberry.common.printer_test import PROBLEM_NOT_FOUND

    impresora = ImpresoraUsbFalsa()
    original = impresora.write

    def se_desenchufa(datos):
        if b"PRUEBA" in datos:
            impresora.conectada = False
        original(datos)

    impresora.write = se_desenchufa
    resultado, _ = probar(impresora)
    assert not resultado.technical_success
    assert resultado.problem == PROBLEM_NOT_FOUND


def test_desconectada_antes_de_probar():
    from fiscalberry.common.printer_test import PROBLEM_NOT_FOUND

    impresora = ImpresoraUsbFalsa()
    impresora.conectada = False
    resultado, _ = probar(impresora)
    assert resultado.problem == PROBLEM_NOT_FOUND


# ---------------------------------------------------------------------------
# build_driver
# ---------------------------------------------------------------------------

CONFIG_GUARDADA = {"driver": "UsbPrint", "idVendor": "0x04b8", "idProduct": "0x0e15",
                   "serial_number": "5839504b3031373431", "_setup_id": "usbprint:04b8:0e15:x"}


def test_fuera_de_windows_usbprint_es_un_error_claro(monkeypatch):
    from fiscalberry.common.ComandosHandler import DriverError, build_driver

    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(DriverError, match="solo está disponible en Windows"):
        build_driver(CONFIG_GUARDADA)


def test_en_windows_build_driver_arma_usbprint(monkeypatch):
    from fiscalberry.common.ComandosHandler import build_driver

    monkeypatch.setattr(sys, "platform", "win32")
    construido = build_driver(dict(CONFIG_GUARDADA, timeout="5"))
    d = construido.driver
    assert isinstance(d, up.UsbPrint) and construido.name == "UsbPrint"
    assert (d.idVendor, d.idProduct) == (0x04B8, 0x0E15)
    assert d.serial_number == "5839504b3031373431" and d.timeout == 5.0
    # No abre nada al construirse (python-escpos abre al primer uso).
    assert d._device is False


def test_candidato_usbprint_desde_la_fabrica_de_171():
    c = PrinterCandidate.usbprint(RUTA_EPSON, 0x04B8, 0x0E15, "5839504b3031373431")
    assert c.status_readable
