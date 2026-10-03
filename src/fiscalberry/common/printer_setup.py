"""
Servicio de configuración de impresoras del asistente (#171).

Capa sin interfaz: detectar, validar, probar y guardar impresoras. La pantalla
del asistente (Kivy) la usa, pero nada de acá importa Kivy, así que se prueba
sin ventana ni hardware.

Dos reglas que este módulo hace cumplir:

- Ninguna impresora se guarda en config.ini antes de que la prueba haya salido
  bien técnicamente Y la persona haya confirmado que el ticket salió en papel.
  Una entrada inválida o una prueba fallida no tocan el archivo.
- Una impresora no se configura dos veces, aunque se la elija por otro camino
  (misma cola de Windows con otro nombre, misma IP, mismo USB).

Transportes (uno por candidato):

| Conexión  | Driver   | Cuándo                                              |
| --------- | -------- | --------------------------------------------------- |
| windows   | Win32Raw | Cola de Windows ya instalada (escenario 4).         |
| network   | Network  | TCP 9100 directo (escenario 1).                     |
| usbprint  | UsbPrint | USB clase impresora por usbprint.sys (escenario 2). |
| serial    | Serial   | USB que Windows muestra como COM (escenario 3).     |
| usb       | Usb      | PyUSB, solo para dispositivos que ya exponen WinUSB.|
"""

import ipaddress
import socket
from contextlib import nullcontext
from dataclasses import dataclass, field

# Conexiones.
WINDOWS = "windows"
NETWORK = "network"
USBPRINT = "usbprint"
SERIAL = "serial"
USB = "usb"

# Puede leerse el estado real de la impresora (DLE EOT: papel, tapa, fuera de
# línea). Por una cola de Windows no: el spooler es unidireccional y dice
# "Lista" aunque la impresora esté apagada.
_ESTADO_LEGIBLE = {
    WINDOWS: False,
    NETWORK: True,
    USBPRINT: True,
    SERIAL: True,
    USB: True,
}

# Puerto de impresión directa (RAW / JetDirect) de casi todas las térmicas.
PUERTO_RAW = 9100

# Python-escpos espera 60 s por defecto a que conecte una impresora de red: con
# la impresora apagada, cada ticket colgaba un minuto la cola. Se guarda este.
NETWORK_TIMEOUT_SEGUNDOS = 10

# Tope de cualquier diagnóstico de red del asistente.
PROBE_TIMEOUT_MAXIMO = 3.0

# Resultados de probe_tcp().
TCP_OK = "ok"
TCP_RECHAZADO = "rechazado"
TCP_SIN_RESPUESTA = "sin_respuesta"
TCP_INVALIDO = "invalido"


class SetupValidationError(ValueError):
    pass


class ConfirmationRequiredError(SetupValidationError):
    pass


class DuplicatePrinterError(SetupValidationError):
    """La impresora ya está guardada. `existente` es el nombre con que está."""

    def __init__(self, mensaje, existente=None):
        super().__init__(mensaje)
        self.existente = existente


class SetupPersistenceError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Candidatos
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PrinterCandidate:
    """
    Una impresora encontrada (o ingresada) que todavía no se guardó.

    - `stable_id`: identidad que no cambia entre arranques ni al cambiar de
      puerto USB. Se guarda como `_setup_id` y es la base del antiduplicados.
    - `driver_config`: exactamente lo que va a config.ini (todo texto).
    - `ubicacion`: dónde está ahora (ruta del dispositivo, puerto COM). Sirve
      para probarla, pero no se guarda: cambia al enchufarla en otro USB.
    """

    display_name: str
    connection: str
    stable_id: str
    driver_config: dict
    detail: str = ""
    ubicacion: str = ""
    capacidades: dict = field(default_factory=dict)

    @property
    def status_readable(self):
        return bool(self.capacidades.get("status_readable"))

    @classmethod
    def _crear(cls, connection, **kwargs):
        return cls(connection=connection,
                   capacidades={"status_readable": _ESTADO_LEGIBLE[connection]},
                   **kwargs)

    @classmethod
    def windows_queue(cls, printer_name, port_name=""):
        name = str(printer_name).strip()
        if not name:
            raise SetupValidationError("La cola de Windows no tiene nombre")
        return cls._crear(
            WINDOWS,
            display_name=name,
            # Windows no distingue mayúsculas en los nombres de cola.
            stable_id=f"windows:{name.casefold()}",
            driver_config={"driver": "Win32Raw", "printer_name": name},
            detail=str(port_name).strip(),
        )

    @classmethod
    def network(cls, host, port=PUERTO_RAW):
        address = _ipv4(host)
        port_value = _puerto(port)
        host_normalized = str(address)
        return cls._crear(
            NETWORK,
            display_name=host_normalized,
            stable_id=f"network:{host_normalized}:{port_value}",
            driver_config={
                "driver": "Network",
                "host": host_normalized,
                "port": str(port_value),
                "timeout": str(NETWORK_TIMEOUT_SEGUNDOS),
            },
            detail=f"Puerto {port_value}",
        )

    @classmethod
    def usbprint(cls, vendor_id, product_id, serial="", device_path=""):
        """USB clase impresora, directo por usbprint.sys (#183)."""
        vendor, product, serie = _usb_identidad(vendor_id, product_id, serial)
        config = {
            "driver": "UsbPrint",
            "idVendor": f"0x{vendor:04x}",
            "idProduct": f"0x{product:04x}",
        }
        if serie:
            config["serial"] = serie
        ubicacion = str(device_path or "").strip()
        return cls._crear(
            USBPRINT,
            display_name=f"USB {vendor:04X}:{product:04X}",
            stable_id=_id_usb(vendor, product, serie, ubicacion),
            driver_config=config,
            detail=serie,
            ubicacion=ubicacion,
        )

    @classmethod
    def serial(cls, port, vendor_id=None, product_id=None, serial="", baudrate=9600):
        """USB que aparece como puerto COM (CDC, CH340, PL2303, FTDI)."""
        puerto = str(port or "").strip()
        if not puerto:
            raise SetupValidationError("Falta el puerto serie (por ejemplo COM3)")
        try:
            baudios = int(baudrate)
        except (TypeError, ValueError) as error:
            raise SetupValidationError("La velocidad del puerto no es válida") from error
        if baudios <= 0:
            raise SetupValidationError("La velocidad del puerto no es válida")

        identidad = f"serial:{puerto.casefold()}"
        detalle = puerto
        if vendor_id is not None and product_id is not None:
            vendor, product, serie = _usb_identidad(vendor_id, product_id, serial)
            detalle = f"{puerto} · USB {vendor:04X}:{product:04X}"
            if serie:
                # El número de COM puede cambiar al enchufarla en otro USB: si
                # el adaptador tiene número de serie, la identidad es él. Sin
                # serie (CH340 y muchos PL2303) dos adaptadores iguales solo se
                # distinguen por el puerto.
                identidad = f"serial:{vendor:04x}:{product:04x}:{serie}"
        return cls._crear(
            SERIAL,
            display_name=puerto,
            stable_id=identidad,
            driver_config={"driver": "Serial", "devfile": puerto,
                           "baudrate": str(baudios)},
            detail=detalle,
            ubicacion=puerto,
        )

    @classmethod
    def usb(cls, vendor_id, product_id, serial=""):
        """PyUSB: solo para dispositivos que ya exponen WinUSB (o en Linux)."""
        vendor, product, serie = _usb_identidad(vendor_id, product_id, serial)
        return cls._crear(
            USB,
            display_name=f"USB {vendor:04X}:{product:04X}",
            stable_id=_id_usb(vendor, product, serie),
            driver_config={
                "driver": "Usb",
                "idVendor": f"0x{vendor:04x}",
                "idProduct": f"0x{product:04x}",
            },
            detail=serie,
        )


def _ipv4(host):
    valor = str(host).strip()
    try:
        address = ipaddress.ip_address(valor)
    except ValueError as error:
        raise SetupValidationError("Ingresá una dirección IP válida") from error
    if address.version != 4:
        raise SetupValidationError("Por ahora se admite únicamente IPv4")
    # 0.0.0.0, multicast y el broadcast de todas las redes no son de un equipo.
    if address.is_unspecified or address.is_multicast or int(address) == 0xFFFFFFFF:
        raise SetupValidationError("Esa dirección no puede ser una impresora")
    return address


def _puerto(port):
    try:
        valor = int(port)
    except (TypeError, ValueError) as error:
        raise SetupValidationError("El puerto debe ser un número") from error
    if not 1 <= valor <= 65535:
        raise SetupValidationError("El puerto debe estar entre 1 y 65535")
    return valor


def validar_direccion(host, port=PUERTO_RAW):
    """(IPv4 normalizada, puerto) o SetupValidationError con el motivo."""
    return str(_ipv4(host)), _puerto(port)


def _usb_id(value, label):
    """
    VID/PID de USB. Se escriben siempre en hexadecimal ("04B8", "0x04b8"):
    así los muestran Windows, lsusb y las etiquetas. Un entero ya es el valor.
    """
    try:
        if isinstance(value, str):
            number = int(value.strip(), 16)
        elif isinstance(value, bool):
            raise TypeError("bool")
        else:
            number = int(value)
    except (TypeError, ValueError) as error:
        raise SetupValidationError(f"El ID de {label} no es válido") from error
    if not 0 <= number <= 0xFFFF:
        raise SetupValidationError(f"El ID de {label} no es válido")
    return number


def _usb_identidad(vendor_id, product_id, serial):
    return (_usb_id(vendor_id, "fabricante"), _usb_id(product_id, "producto"),
            str(serial or "").strip())


def _id_usb(vendor, product, serie, ubicacion=""):
    """
    Identidad de un dispositivo USB, la vea usbprint.sys o PyUSB: es el mismo
    aparato, y elegirlo por los dos caminos no puede configurarlo dos veces.

    Con número de serie, la identidad es VID:PID:serie y sobrevive a cambiarlo
    de puerto. Sin serie, dos impresoras iguales (cocina y barra del mismo
    modelo) solo se distinguen por dónde están enchufadas.
    """
    identidad = f"usb:{vendor:04x}:{product:04x}"
    if serie:
        return f"{identidad}:{serie}"
    if ubicacion:
        return f"{identidad}@{ubicacion.casefold()}"
    return identidad


# --------------------------------------------------------------------------
# Diagnóstico rápido de red
# --------------------------------------------------------------------------

def probe_tcp(host, port=PUERTO_RAW, timeout=PROBE_TIMEOUT_MAXIMO, conectar=None):
    """
    ¿Hay algo escuchando en host:port? Antes de imprimir, para explicar rápido.

    Returns:
        TCP_OK, TCP_RECHAZADO (el equipo existe y responde, pero no en ese
        puerto), TCP_SIN_RESPUESTA (apagado, otra red o un firewall) o
        TCP_INVALIDO (los datos no son una IPv4 y un puerto).

    Nunca espera más de PROBE_TIMEOUT_MAXIMO: el asistente no puede quedarse
    colgado preguntando por una IP que no existe.
    """
    try:
        destino = (str(_ipv4(host)), _puerto(port))
    except SetupValidationError:
        return TCP_INVALIDO

    conectar = conectar or socket.create_connection
    espera = max(0.1, min(float(timeout), PROBE_TIMEOUT_MAXIMO))
    try:
        conexion = conectar(destino, espera)
    except ConnectionRefusedError:
        return TCP_RECHAZADO
    except (socket.timeout, TimeoutError):
        return TCP_SIN_RESPUESTA
    except OSError:
        # Red inalcanzable, host inalcanzable: para el usuario es lo mismo.
        return TCP_SIN_RESPUESTA
    try:
        conexion.close()
    except OSError:
        pass
    return TCP_OK


# --------------------------------------------------------------------------
# Guardar
# --------------------------------------------------------------------------

def validar_nombre(alias):
    """
    Nombre con que el backend va a pedir imprimir en esta impresora.

    No alcanza con que no esté vacío: Configberry.get_config_for_printer()
    interpreta el printerName antes de buscar la sección. Un nombre con ":"
    se toma como IP:puerto, uno con "=" como configuración en línea y uno con
    tres puntos como una IP: con esos nombres la impresora quedaría guardada
    pero ningún ticket llegaría nunca a ella.
    """
    nombre = str(alias or "").strip()
    if not nombre:
        raise SetupValidationError("Elegí un nombre para la impresora")
    if nombre.casefold() in PrinterSetupService.RESERVED_SECTIONS:
        raise SetupValidationError("Ese nombre está reservado: elegí otro")
    if any(c in nombre for c in ":=[]\r\n"):
        raise SetupValidationError(
            "El nombre no puede tener ninguno de estos signos: : = [ ]")
    if nombre.count(".") == 3:
        raise SetupValidationError(
            "El nombre no puede parecer una dirección IP: elegí otro")
    return nombre


class PrinterSetupService:
    # Secciones de config.ini que no son impresoras.
    RESERVED_SECTIONS = {
        "servidor",
        "paxaprinter",
        "rabbitmq",
        "heartbeat",
        "updater",
    }

    def __init__(self, config):
        self.config = config

    def _candado(self):
        # Revisar duplicados y guardar tiene que ser una sola operación: el
        # backend también escribe config.ini (adopción, cambio de comercio).
        return getattr(self.config, "_rlock", None) or nullcontext()

    def buscar_duplicado(self, candidate, current=None):
        """Nombre de la impresora ya guardada que es esta misma, o None."""
        current = self.config.get_actual_config() if current is None else current
        valores = dict(candidate.driver_config, _setup_id=candidate.stable_id)
        huella = _config_fingerprint(valores)
        huella_driver = _driver_fingerprint(valores)
        for seccion, existentes in current.items():
            if seccion.casefold() in self.RESERVED_SECTIONS:
                continue
            if _config_fingerprint(existentes) == huella:
                return seccion
            # Impresoras guardadas antes del asistente (sin _setup_id): solo
            # queda comparar los parámetros del driver.
            if (not str(existentes.get("_setup_id", "")).strip()
                    and huella_driver is not None
                    and _driver_fingerprint(existentes) == huella_driver):
                return seccion
        return None

    def save_confirmed(
        self,
        alias,
        candidate,
        technical_success=False,
        physical_confirmed=False,
    ):
        section = validar_nombre(alias)
        if not technical_success or not physical_confirmed:
            raise ConfirmationRequiredError(
                "La impresora debe superar la prueba y confirmarse en papel"
            )

        with self._candado():
            current = self.config.get_actual_config()
            if any(s.casefold() == section.casefold() for s in current):
                raise DuplicatePrinterError(
                    "Ya existe una impresora con ese nombre", existente=section)

            existente = self.buscar_duplicado(candidate, current)
            if existente:
                raise DuplicatePrinterError(
                    f"Esta impresora ya está configurada como «{existente}»",
                    existente=existente)

            values_to_save = dict(candidate.driver_config)
            values_to_save["_setup_id"] = candidate.stable_id
            if not self.config.set(section, values_to_save):
                raise SetupPersistenceError("No se pudo guardar la impresora")
        return section


def _config_fingerprint(values):
    setup_id = str(values.get("_setup_id", "")).strip()
    if setup_id:
        return "setup", setup_id.casefold()
    return _driver_fingerprint(values)


def _driver_fingerprint(values):
    """Qué dispositivo físico es, según los parámetros del driver."""
    driver = str(values.get("driver", "")).lower()
    if driver == "win32raw":
        return driver, str(values.get("printer_name", "")).strip().casefold()
    if driver == "network":
        return (
            driver,
            str(values.get("host", "")).strip(),
            str(values.get("port", "9100")).strip(),
        )
    if driver in ("usb", "usbprint"):
        try:
            return (
                "usb",
                _usb_id(values.get("idVendor", ""), "fabricante"),
                _usb_id(values.get("idProduct", ""), "producto"),
            )
        except SetupValidationError:
            return None
    if driver == "serial":
        return driver, str(values.get("devfile", "")).strip().casefold()
    return None
