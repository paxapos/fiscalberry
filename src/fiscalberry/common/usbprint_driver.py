"""
Driver UsbPrint: USB directo por usbprint.sys en Windows (#183, escenario 2).

Casi todas las térmicas POS se enumeran como clase Impresora USB (0x07).
Windows carga solo usbprint.sys (viene con Windows) aunque no haya driver de
impresora ni cola. Ese driver expone una interfaz que se abre con CreateFile:
WriteFile manda los bytes ESC/POS y ReadFile trae la respuesta de DLE EOT
cuando la impresora tiene endpoint de entrada. **No hace falta admin ni
cambiar el driver** (PyUSB/libusb exigiría reemplazar usbprint.sys por
WinUSB con Zadig, y eso rompe la cola de Windows: nunca se hace).

- Toda E/S es superpuesta (FILE_FLAG_OVERLAPPED) con timeout: una impresora
  apagada o sin papel puede dejar un WriteFile colgado para siempre.
- Convive con el spooler: si un trabajo de Windows tiene el dispositivo
  abierto, CreateFile falla por "en uso" y se reintenta con backoff. Cada
  ticket abre y cierra (EscposIO autoclose), así que tampoco lo retiene.
- Se guarda la identidad (VID/PID/serie), no la ruta: la ruta incluye el
  puerto físico y cambia si se enchufa en otro. Al abrir se busca de nuevo.
- IOCTL_USBPRINT_GET_LPT_STATUS (papel, seleccionada, error) se lee solo como
  dato informativo: muchas térmicas devuelven siempre el mismo valor, y
  bloquear una prueba por eso daría falsos "sin papel". La verdad es DLE EOT.

La capa de Windows (`Win32File`) va detrás de `kernel32` inyectable: los
tests la ejercitan con un kernel32 falso.
"""

import errno
import time

from escpos.escpos import Escpos

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("UsbPrint")


# -- Códigos de Windows --------------------------------------------------------

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = (1 << 64) - 1  # (HANDLE)-1 visto como c_void_p en 64 bits

ERROR_FILE_NOT_FOUND = 2
ERROR_PATH_NOT_FOUND = 3
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_FUNCTION = 1
ERROR_GEN_FAILURE = 31
ERROR_SHARING_VIOLATION = 32
ERROR_NOT_SUPPORTED = 50
ERROR_BUSY = 170
ERROR_SEM_TIMEOUT = 121
ERROR_OPERATION_ABORTED = 995
ERROR_IO_PENDING = 997
ERROR_DEVICE_NOT_CONNECTED = 1167
ERROR_NO_SUCH_DEVICE = 433
ERROR_TIMEOUT = 1460
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102

# usbprint.h: CTL_CODE(FILE_DEVICE_UNKNOWN, USBPRINT_IOCTL_INDEX + n, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_USBPRINT_GET_LPT_STATUS = 0x220030
IOCTL_USBPRINT_GET_1284_ID = 0x220034

# Errores que significan "otro lo está usando": se reintenta.
BUSY_ERRORS = {ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION, ERROR_BUSY}
# Errores que significan "ya no está": desenchufada o apagada.
GONE_ERRORS = {ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND, ERROR_DEVICE_NOT_CONNECTED,
               ERROR_NO_SUCH_DEVICE, ERROR_GEN_FAILURE}

_ERRNO_DE = {ERROR_FILE_NOT_FOUND: errno.ENOENT, ERROR_PATH_NOT_FOUND: errno.ENOENT,
             ERROR_DEVICE_NOT_CONNECTED: errno.ENODEV, ERROR_NO_SUCH_DEVICE: errno.ENODEV,
             ERROR_GEN_FAILURE: errno.EIO, ERROR_ACCESS_DENIED: errno.EACCES,
             ERROR_SHARING_VIOLATION: errno.EBUSY, ERROR_BUSY: errno.EBUSY}


class WindowsIOError(OSError):
    """OSError con el código de Windows en `winerror`, también fuera de Windows."""

    def __init__(self, winerror, mensaje):
        super().__init__(_ERRNO_DE.get(winerror, errno.EIO), mensaje)
        self.winerror = winerror


class UsbPrintNotFound(WindowsIOError):
    def __init__(self, mensaje):
        super().__init__(ERROR_FILE_NOT_FOUND, mensaje)


# -- kernel32 real -------------------------------------------------------------

def _kernel32_real():
    import ctypes
    from ctypes import c_int, c_uint32, c_void_p, c_wchar_p

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = c_void_p
    k32.CreateFileW.argtypes = [c_wchar_p, c_uint32, c_uint32, c_void_p, c_uint32, c_uint32, c_void_p]
    k32.CreateEventW.restype = c_void_p
    k32.CreateEventW.argtypes = [c_void_p, c_int, c_int, c_wchar_p]
    for nombre in ("WriteFile", "ReadFile"):
        getattr(k32, nombre).argtypes = [c_void_p, c_void_p, c_uint32, c_void_p, c_void_p]
        getattr(k32, nombre).restype = c_int
    k32.DeviceIoControl.argtypes = [c_void_p, c_uint32, c_void_p, c_uint32, c_void_p, c_uint32,
                                    c_void_p, c_void_p]
    k32.DeviceIoControl.restype = c_int
    k32.WaitForSingleObject.argtypes = [c_void_p, c_uint32]
    k32.WaitForSingleObject.restype = c_uint32
    k32.GetOverlappedResult.argtypes = [c_void_p, c_void_p, c_void_p, c_int]
    k32.GetOverlappedResult.restype = c_int
    k32.CancelIoEx.argtypes = [c_void_p, c_void_p]
    k32.CancelIoEx.restype = c_int
    k32.CloseHandle.argtypes = [c_void_p]
    k32.CloseHandle.restype = c_int
    k32.last_error = ctypes.get_last_error
    return k32


def _overlapped_type():
    import ctypes
    from ctypes import Structure, c_uint32, c_void_p

    class OVERLAPPED(Structure):
        _fields_ = [("Internal", c_void_p), ("InternalHigh", c_void_p),
                    ("Offset", c_uint32), ("OffsetHigh", c_uint32), ("hEvent", c_void_p)]
    return OVERLAPPED, ctypes


class Win32File:
    """
    Un dispositivo abierto con CreateFile y E/S superpuesta con timeout.

    `timeout` es la espera de las lecturas (read_status la acorta mientras
    consulta el estado, igual que con un puerto serie).
    """

    def __init__(self, path, kernel32=None, timeout=2.0, write_timeout=10.0):
        self.path = path
        self.k32 = kernel32 or _kernel32_real()
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._ov_type, self._ct = _overlapped_type()
        handle = self.k32.CreateFileW(
            path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        if not handle or handle in (INVALID_HANDLE_VALUE, -1):
            codigo = self.k32.last_error()
            raise WindowsIOError(codigo, f"No se pudo abrir la impresora USB (error {codigo})")
        self.handle = handle

    # -- E/S ---------------------------------------------------------------

    def _io(self, llamar, timeout, que):
        """Corre una operación superpuesta y devuelve los bytes transferidos."""
        ct = self._ct
        ov = self._ov_type()
        evento = self.k32.CreateEventW(None, True, False, None)
        if not evento:
            raise WindowsIOError(self.k32.last_error(), "No se pudo crear el evento de E/S")
        ov.hEvent = evento
        transferidos = ct.c_uint32(0)
        try:
            ok = llamar(ct.byref(transferidos), ct.byref(ov))
            if ok:
                return transferidos.value
            codigo = self.k32.last_error()
            if codigo != ERROR_IO_PENDING:
                raise WindowsIOError(codigo, f"{que} falló (error {codigo})")
            espera = self.k32.WaitForSingleObject(evento, max(1, int(timeout * 1000)))
            if espera == WAIT_TIMEOUT:
                self.k32.CancelIoEx(self.handle, ct.byref(ov))
                # Esperar a que la cancelación termine: el buffer y el OVERLAPPED
                # tienen que seguir vivos hasta entonces.
                self.k32.GetOverlappedResult(self.handle, ct.byref(ov), ct.byref(transferidos), True)
                raise TimeoutError(f"{que}: la impresora no respondió en {timeout:g} s")
            if espera != WAIT_OBJECT_0:
                raise WindowsIOError(self.k32.last_error(), f"{que}: espera fallida")
            if not self.k32.GetOverlappedResult(self.handle, ct.byref(ov),
                                                ct.byref(transferidos), False):
                codigo = self.k32.last_error()
                if codigo in (ERROR_SEM_TIMEOUT, ERROR_TIMEOUT):
                    raise TimeoutError(f"{que}: la impresora no respondió")
                raise WindowsIOError(codigo, f"{que} falló (error {codigo})")
            return transferidos.value
        finally:
            self.k32.CloseHandle(evento)

    def write(self, data):
        data = bytes(data)
        enviados = 0
        while enviados < len(data):
            trozo = data[enviados:]
            buffer = self._ct.create_string_buffer(trozo, len(trozo))
            n = self._io(lambda t, ov: self.k32.WriteFile(self.handle, buffer, len(trozo), t, ov),
                         self.write_timeout, "Enviar a la impresora")
            if n <= 0:
                raise TimeoutError("La impresora USB no aceptó los datos")
            enviados += n
        return enviados

    def read(self, size=64):
        buffer = self._ct.create_string_buffer(size)
        n = self._io(lambda t, ov: self.k32.ReadFile(self.handle, buffer, size, t, ov),
                     self.timeout, "Leer de la impresora")
        return buffer.raw[:n]

    def ioctl(self, code, out_size, timeout=1.0):
        buffer = self._ct.create_string_buffer(out_size)
        n = self._io(lambda t, ov: self.k32.DeviceIoControl(self.handle, code, None, 0, buffer,
                                                            out_size, t, ov),
                     timeout, "Consultar la impresora")
        return buffer.raw[:n]

    def close(self):
        if getattr(self, "handle", None):
            try:
                self.k32.CloseHandle(self.handle)
            finally:
                self.handle = None


# -- IEEE 1284 y LPT -------------------------------------------------------------

def parse_1284_id(respuesta):
    """
    {clave: valor} de un Device ID IEEE 1284 ("MFG:EPSON;MDL:TM-T20II;...").
    La respuesta del IOCTL trae 2 bytes de largo (big-endian) adelante.
    """
    datos = bytes(respuesta or b"")
    if len(datos) >= 2:
        largo = int.from_bytes(datos[:2], "big")
        if 2 < largo <= len(datos):
            datos = datos[2:largo]
        else:
            datos = datos[2:]
    texto = datos.decode("latin-1", errors="replace").strip("\x00 ")
    campos = {}
    for parte in texto.split(";"):
        if ":" in parte:
            clave, valor = parte.split(":", 1)
            campos[clave.strip().upper()] = valor.strip()
    for largo, corto in (("MANUFACTURER", "MFG"), ("MODEL", "MDL"),
                         ("COMMAND SET", "CMD"), ("DESCRIPTION", "DES")):
        if largo in campos and corto not in campos:
            campos[corto] = campos[largo]
    return campos


def model_from_1284(campos):
    """"EPSON TM-T20II" a partir del Device ID, o "" si no dice nada útil."""
    fabricante = campos.get("MFG", "").strip()
    modelo = campos.get("MDL", "").strip() or campos.get("DES", "").strip()
    if not modelo:
        return ""
    if fabricante and not modelo.lower().startswith(fabricante.lower()):
        return f"{fabricante} {modelo}"
    return modelo


LPT_PAPER_EMPTY = 0x20
LPT_SELECTED = 0x10
LPT_NOT_ERROR = 0x08


def parse_lpt_status(valor):
    """Bits del registro de estado de puerto paralelo (solo informativo)."""
    if valor is None:
        return {}
    return {"sin_papel": bool(valor & LPT_PAPER_EMPTY),
            "seleccionada": bool(valor & LPT_SELECTED),
            "error": not (valor & LPT_NOT_ERROR)}


# -- El driver --------------------------------------------------------------------

BUSY_BACKOFF = (0.25, 0.5, 1.0, 2.0)


def _como_id(valor):
    if valor is None or valor == "":
        return None
    return int(valor, 0) if isinstance(valor, str) else int(valor)


class UsbPrint(Escpos):
    """
    Impresora USB por usbprint.sys. Se construye con lo que guarda el
    asistente: idVendor, idProduct y serial_number (o device_path si la
    impresora no tiene número de serie).
    """

    def __init__(self, idVendor=None, idProduct=None, serial_number="", device_path="",
                 timeout=10, kernel32=None, enumerate_devices=None, sleep=time.sleep,
                 busy_backoff=BUSY_BACKOFF, *args, **kwargs):
        Escpos.__init__(self, *args, **kwargs)
        self.idVendor = _como_id(idVendor)
        self.idProduct = _como_id(idProduct)
        self.serial_number = str(serial_number or "").strip()
        self.device_path = str(device_path or "").strip()
        self.timeout = float(timeout)
        self._kernel32 = kernel32
        self._enumerate = enumerate_devices
        self._sleep = sleep
        self._backoff = tuple(busy_backoff)
        self.resolved_path = ""

    # -- encontrar el dispositivo -----------------------------------------

    def _dispositivos(self):
        if self._enumerate is not None:
            return list(self._enumerate())
        from fiscalberry.common.usb_discovery import list_usbprint_devices
        return list_usbprint_devices(with_details=False)

    def _coincide(self, d):
        if self.idVendor is not None and d.vendor_id != self.idVendor:
            return False
        if self.idProduct is not None and d.product_id != self.idProduct:
            return False
        if self.serial_number and d.serial.lower() != self.serial_number.lower():
            return False
        return True

    def resolve_path(self):
        """
        La ruta actual de la impresora. Con número de serie se busca por
        identidad; sin él, se usa la ruta guardada y, si la impresora cambió
        de puerto, la única con ese VID/PID.
        """
        dispositivos = self._dispositivos()
        if self.device_path:
            for d in dispositivos:
                if d.device_path.lower() == self.device_path.lower():
                    return d.device_path
        candidatos = [d for d in dispositivos if self._coincide(d)]
        if len(candidatos) == 1:
            return candidatos[0].device_path
        if not candidatos:
            raise UsbPrintNotFound("La impresora USB no está conectada")
        raise UsbPrintNotFound(
            "Hay varias impresoras USB iguales y no se sabe cuál es: "
            "conectala en el mismo puerto USB en que se configuró")

    # -- Escpos -------------------------------------------------------------

    def open(self, raise_not_found=True):
        ruta = self.resolve_path()
        intentos = (0.0,) + self._backoff
        ultimo = None
        for i, espera in enumerate(intentos):
            if espera:
                self._sleep(espera)
            try:
                self.device = Win32File(ruta, self._kernel32, write_timeout=self.timeout)
                self.resolved_path = ruta
                return
            except WindowsIOError as e:
                ultimo = e
                if e.winerror not in BUSY_ERRORS:
                    raise
                logger.debug(f"UsbPrint ocupada (error {e.winerror}), reintento {i + 1}")
        raise ultimo

    def _raw(self, msg):
        self.device.write(msg)

    def _read(self):
        return self.device.read(64)

    def close(self):
        dispositivo = getattr(self, "_device", False)
        if dispositivo:
            try:
                dispositivo.close()
            except Exception as e:
                logger.debug(f"Error cerrando UsbPrint: {e}")
        self._device = False

    # -- extras de usbprint -------------------------------------------------

    def lpt_status(self):
        """Estado LPT (dict informativo) o {} si el dispositivo no lo da."""
        try:
            respuesta = self.device.ioctl(IOCTL_USBPRINT_GET_LPT_STATUS, 1)
        except (OSError, TimeoutError) as e:
            logger.debug(f"UsbPrint sin estado LPT: {e}")
            return {}
        return parse_lpt_status(respuesta[0] if respuesta else None)

    def device_id(self):
        try:
            return parse_1284_id(self.device.ioctl(IOCTL_USBPRINT_GET_1284_ID, 1024))
        except (OSError, TimeoutError) as e:
            logger.debug(f"UsbPrint sin Device ID: {e}")
            return {}
