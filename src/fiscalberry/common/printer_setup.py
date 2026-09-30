"""
Servicio de configuración de impresoras (#171).

Capa sin Kivy ni hardware entre lo que se detecta (colas de Windows #174, red
#175, USB/COM #183) o lo que ingresa el usuario, y el config.ini. Su regla
central: **ninguna impresora se guarda antes del éxito técnico y la
confirmación física en papel** (ver printer_test.py, #172).

Un `PrinterCandidate` describe una impresora posible, sin tocar nada:

| Transporte | Driver   | Escenario de #170        | Estado real (DLE EOT)              |
|------------|----------|--------------------------|------------------------------------|
| Win32Raw   | Win32Raw | 4: cola ya instalada     | No: el spooler es unidireccional   |
| Network    | Network  | 1 y 5: TCP 9100 directo  | Sí                                 |
| UsbPrint   | UsbPrint | 2: USB por usbprint.sys  | Sí (driver en #183)                |
| Serial     | Serial   | 3: USB que aparece como COM | Sí                              |
| Usb        | Usb      | PyUSB, solo si ya expone WinUSB | Sí                          |

Las claves que empiezan con "_" (`_setup_id`, `_usb_vid`, ...) son metadata del
asistente: se guardan en el config.ini pero nunca llegan al constructor del
driver (ComandosHandler.build_driver las descarta).
"""

from dataclasses import dataclass, field
import ipaddress
import socket


class SetupValidationError(ValueError):
    pass


class ConfirmationRequiredError(SetupValidationError):
    pass


class DuplicatePrinterError(SetupValidationError):
    """
    La impresora (o el nombre) ya está configurada. `existing_alias` dice
    cuál, para que la interfaz pueda ofrecer algo concreto ("ya está guardada
    como Cocina") en vez de un error.
    """

    def __init__(self, message, existing_alias=None):
        super().__init__(message)
        self.existing_alias = existing_alias


class SetupPersistenceError(RuntimeError):
    pass


# -- Transportes -------------------------------------------------------------

TRANSPORT_WIN32RAW = "Win32Raw"
TRANSPORT_NETWORK = "Network"
TRANSPORT_USBPRINT = "UsbPrint"
TRANSPORT_SERIAL = "Serial"
TRANSPORT_USB = "Usb"

TRANSPORTS = (
    TRANSPORT_WIN32RAW,
    TRANSPORT_NETWORK,
    TRANSPORT_USBPRINT,
    TRANSPORT_SERIAL,
    TRANSPORT_USB,
)

# Capacidades
CAP_STATUS_READABLE = "status_readable"

# Los transportes bidireccionales permiten leer el estado real con DLE EOT
# (fuera de línea, tapa abierta, sin papel). Por una cola de Windows no: el
# spooler solo manda bytes hacia la impresora.
_STATUS_READABLE = frozenset({CAP_STATUS_READABLE})

# El default de python-escpos es 60 s: con la impresora apagada, cada ticket
# quedaría un minuto colgado antes de fallar y reintentarse.
NETWORK_TIMEOUT_SECONDS = 10
DEFAULT_RAW_PORT = 9100
DEFAULT_SERIAL_BAUDRATE = 9600

CONNECTION_LABELS = {
    TRANSPORT_WIN32RAW: "Cola de Windows",
    TRANSPORT_NETWORK: "Red",
    TRANSPORT_USBPRINT: "USB",
    TRANSPORT_SERIAL: "Puerto serie",
    TRANSPORT_USB: "USB",
}


@dataclass(frozen=True)
class PrinterCandidate:
    """
    Una impresora posible, todavía sin guardar.

    - `stable_id`: identidad que sobrevive a reinicios y cambios de puerto;
      detecta duplicados y queda guardada como `_setup_id`.
    - `transport`: uno de TRANSPORTS; coincide con el driver.
    - `connection`: categoría para la interfaz (windows, network, usb, serial).
    - `driver_config`: lo que recibe el driver para imprimir AHORA (la prueba).
    - `runtime_only`: claves de driver_config que sirven para la prueba pero
      no se guardan (la ruta de un dispositivo USB cambia al cambiar de puerto).
    """

    display_name: str
    connection: str
    stable_id: str
    driver_config: dict
    detail: str = ""
    transport: str = ""
    capabilities: frozenset = field(default_factory=frozenset)
    runtime_only: frozenset = field(default_factory=frozenset)

    @property
    def status_readable(self):
        return CAP_STATUS_READABLE in self.capabilities

    @property
    def connection_label(self):
        """Tipo de conexión en palabras (va impreso en el ticket de prueba)."""
        etiqueta = CONNECTION_LABELS.get(self.transport, self.transport or "Impresora")
        return f"{etiqueta} ({self.detail})" if self.detail else etiqueta

    def config_to_persist(self):
        """Lo que se escribe en el config.ini si la prueba sale bien."""
        valores = {k: v for k, v in self.driver_config.items() if k not in self.runtime_only}
        valores["_setup_id"] = self.stable_id
        return valores

    # -- Fábricas por transporte ------------------------------------------

    @classmethod
    def windows_queue(cls, printer_name, port_name=""):
        """Escenario 4: una cola de Windows que ya existe (no se crea nada)."""
        name = str(printer_name).strip()
        if not name:
            raise SetupValidationError("La cola de Windows no tiene nombre")
        return cls(
            display_name=name,
            connection="windows",
            stable_id=f"windows:{name}",
            driver_config={"driver": TRANSPORT_WIN32RAW, "printer_name": name},
            detail=str(port_name).strip(),
            transport=TRANSPORT_WIN32RAW,
        )

    @classmethod
    def network(cls, host, port=DEFAULT_RAW_PORT):
        """Escenarios 1 y 5: TCP directo al puerto RAW de la impresora."""
        host_normalized, port_value = validate_network_address(host, port)
        return cls(
            display_name=host_normalized,
            connection="network",
            stable_id=f"network:{host_normalized}:{port_value}",
            driver_config={
                "driver": TRANSPORT_NETWORK,
                "host": host_normalized,
                "port": str(port_value),
                "timeout": str(NETWORK_TIMEOUT_SECONDS),
            },
            detail=host_normalized if port_value == DEFAULT_RAW_PORT
            else f"{host_normalized}:{port_value}",
            transport=TRANSPORT_NETWORK,
            capabilities=_STATUS_READABLE,
        )

    @classmethod
    def usbprint(cls, device_path, vendor_id, product_id, serial=""):
        """
        Escenario 2: USB clase impresora por usbprint.sys, sin driver ni cola.

        Se guarda la identidad (VID/PID/serie), no la ruta del dispositivo: la
        ruta incluye el puerto USB físico y cambia si se enchufa en otro. La
        ruta solo se usa para la prueba. El driver llega con #183.
        """
        ruta = str(device_path or "").strip()
        if not ruta:
            raise SetupValidationError("El dispositivo USB no tiene ruta")
        vendor = _usb_id(vendor_id, "fabricante")
        product = _usb_id(product_id, "producto")
        serial_value = str(serial or "").strip()

        config = {
            "driver": TRANSPORT_USBPRINT,
            "idVendor": f"0x{vendor:04x}",
            "idProduct": f"0x{product:04x}",
            "device_path": ruta,
        }
        if serial_value:
            config["serial_number"] = serial_value
            identity = f"usbprint:{vendor:04x}:{product:04x}:{serial_value}"
            runtime_only = frozenset({"device_path"})
        else:
            # Sin número de serie, dos impresoras iguales solo se distinguen
            # por el puerto: la ruta es parte de la identidad y se guarda.
            identity = f"usbprint:{vendor:04x}:{product:04x}@{ruta.lower()}"
            runtime_only = frozenset()

        return cls(
            display_name=f"USB {vendor:04X}:{product:04X}",
            connection="usb",
            stable_id=identity,
            driver_config=config,
            detail=serial_value,
            transport=TRANSPORT_USBPRINT,
            capabilities=_STATUS_READABLE,
            runtime_only=runtime_only,
        )

    @classmethod
    def serial(cls, port, baudrate=DEFAULT_SERIAL_BAUDRATE, vendor_id=None,
               product_id=None, serial_number=""):
        """
        Escenario 3: USB que Windows presenta como puerto COM (CDC, CH340,
        PL2303, FTDI). El VID/PID/serie se guardan como metadata para poder
        reencontrar la impresora si cambia el número de COM.
        """
        devfile = str(port or "").strip()
        if not devfile:
            raise SetupValidationError("Falta el puerto serie")
        if devfile.upper().startswith("COM"):
            devfile = devfile.upper()
        try:
            baud = int(baudrate)
        except (TypeError, ValueError) as error:
            raise SetupValidationError("La velocidad del puerto debe ser un número") from error
        if baud <= 0:
            raise SetupValidationError("La velocidad del puerto debe ser mayor a cero")

        config = {"driver": TRANSPORT_SERIAL, "devfile": devfile, "baudrate": str(baud)}
        serial_value = str(serial_number or "").strip()
        if vendor_id is not None and product_id is not None:
            vendor = _usb_id(vendor_id, "fabricante")
            product = _usb_id(product_id, "producto")
            config["_usb_vid"] = f"0x{vendor:04x}"
            config["_usb_pid"] = f"0x{product:04x}"
            if serial_value:
                config["_usb_serial"] = serial_value
                identity = f"serial:{vendor:04x}:{product:04x}:{serial_value}"
            else:
                identity = f"serial:{vendor:04x}:{product:04x}@{devfile}"
        else:
            identity = f"serial:{devfile}"

        return cls(
            display_name=devfile,
            connection="serial",
            stable_id=identity,
            driver_config=config,
            detail=devfile,
            transport=TRANSPORT_SERIAL,
            capabilities=_STATUS_READABLE,
        )

    @classmethod
    def usb(cls, vendor_id, product_id, serial=""):
        """
        PyUSB directo. Solo sirve para dispositivos que ya exponen WinUSB: una
        impresora de clase USB Printer usa usbprint.sys (ver `usbprint`), y
        reemplazar ese driver rompería su cola de Windows.
        """
        vendor = _usb_id(vendor_id, "fabricante")
        product = _usb_id(product_id, "producto")
        serial_value = str(serial).strip()
        identity = f"usb:{vendor:04x}:{product:04x}"
        if serial_value:
            identity += f":{serial_value}"
        return cls(
            display_name=f"USB {vendor:04X}:{product:04X}",
            connection="usb",
            stable_id=identity,
            driver_config={
                "driver": TRANSPORT_USB,
                "idVendor": f"0x{vendor:04x}",
                "idProduct": f"0x{product:04x}",
            },
            detail=serial_value,
            transport=TRANSPORT_USB,
            capabilities=_STATUS_READABLE,
        )


# -- Diagnóstico de red ------------------------------------------------------

TCP_OK = "ok"
TCP_REFUSED = "rechazado"
TCP_NO_RESPONSE = "sin_respuesta"
TCP_INVALID = "invalido"

# Ningún diagnóstico de red espera más que esto (#171).
MAX_PROBE_TIMEOUT = 3.0


def probe_tcp(host, port=DEFAULT_RAW_PORT, timeout=MAX_PROBE_TIMEOUT, socket_factory=None):
    """
    Diagnóstico rápido antes de imprimir: ¿hay algo escuchando en host:port?

    - TCP_OK: la impresora aceptó la conexión.
    - TCP_REFUSED: el equipo respondió pero ese puerto está cerrado (otra
      cosa en esa IP, o el puerto RAW deshabilitado).
    - TCP_NO_RESPONSE: nadie contestó a tiempo: apagada, desconectada, en
      otra subred o IP equivocada.
    - TCP_INVALID: los datos no son una dirección válida; no se intenta nada.

    Nunca espera más de MAX_PROBE_TIMEOUT. `socket_factory` permite probarlo
    sin red.
    """
    try:
        host_normalized, port_value = validate_network_address(host, port)
    except SetupValidationError:
        return TCP_INVALID

    try:
        espera = float(timeout)
    except (TypeError, ValueError):
        espera = MAX_PROBE_TIMEOUT
    if not 0 < espera <= MAX_PROBE_TIMEOUT:
        espera = MAX_PROBE_TIMEOUT

    factory = socket_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    try:
        sock = factory()
    except OSError:
        return TCP_NO_RESPONSE
    try:
        sock.settimeout(espera)
        sock.connect((host_normalized, port_value))
        return TCP_OK
    except (ConnectionRefusedError, ConnectionResetError):
        return TCP_REFUSED
    except OSError:
        # Incluye el timeout y "no hay ruta al host".
        return TCP_NO_RESPONSE
    finally:
        try:
            sock.close()
        except OSError:
            pass


def validate_network_address(host, port=DEFAULT_RAW_PORT):
    """Normaliza (host IPv4, puerto) o lanza SetupValidationError."""
    host_value = str(host).strip()
    try:
        address = ipaddress.ip_address(host_value)
    except ValueError as error:
        raise SetupValidationError("Ingresá una dirección IP válida") from error
    if address.version != 4:
        raise SetupValidationError("Por ahora se admite únicamente IPv4")
    if address.is_unspecified or address.is_multicast or address == ipaddress.ip_address("255.255.255.255"):
        raise SetupValidationError("Esa dirección no puede ser una impresora")

    try:
        port_value = int(port)
    except (TypeError, ValueError) as error:
        raise SetupValidationError("El puerto debe ser un número") from error
    if not 1 <= port_value <= 65535:
        raise SetupValidationError("El puerto debe estar entre 1 y 65535")
    return str(address), port_value


# -- Servicio ----------------------------------------------------------------

class PrinterSetupService:
    """
    Guarda impresoras confirmadas en el config.ini (vía Configberry.set, que
    escribe de forma atómica). No importa nada de la interfaz.
    """

    # Secciones del config.ini que no son impresoras.
    RESERVED_SECTIONS = {
        "servidor",
        "paxaprinter",
        "rabbitmq",
        "heartbeat",
        "updater",
    }

    ALIAS_MAX_LENGTH = 40

    def __init__(self, config):
        self.config = config

    # -- consultas --------------------------------------------------------

    def configured_printers(self):
        """{alias: valores} de las secciones que son impresoras válidas."""
        return {
            section: values
            for section, values in self.config.get_actual_config().items()
            if section.lower() not in self.RESERVED_SECTIONS
            and is_valid_printer_config(values)
        }

    def has_configured_printers(self):
        return bool(self.configured_printers())

    def find_duplicate(self, candidate):
        """
        Alias de la impresora ya guardada que es la misma, o None.

        Se compara por identidad estable (`_setup_id`) y por dirección: la
        misma cola de Windows (sin distinguir mayúsculas, como Windows), el
        mismo host:puerto o el mismo puerto COM son la misma impresora aunque
        se hayan guardado de otra forma. En USB la dirección (VID/PID) no
        alcanza —dos térmicas iguales la comparten—, así que solo se usa contra
        impresoras guardadas antes del asistente, que no tienen `_setup_id`.
        """
        values = candidate.config_to_persist()
        fingerprint = _driver_fingerprint(values)
        for section, current in self.config.get_actual_config().items():
            if section.lower() in self.RESERVED_SECTIONS:
                continue
            setup_id = str(current.get("_setup_id", "")).strip()
            if setup_id and setup_id == candidate.stable_id:
                return section
            if fingerprint is None or _driver_fingerprint(current) != fingerprint:
                continue
            if fingerprint[0] in _ADDRESS_IS_IDENTITY or not setup_id:
                return section
        return None

    def validate_alias(self, alias):
        """Devuelve el alias normalizado o lanza SetupValidationError."""
        section = " ".join(str(alias or "").split())
        if not section:
            raise SetupValidationError("Elegí un nombre para la impresora")
        if section.lower() in self.RESERVED_SECTIONS:
            raise SetupValidationError("Ese nombre está reservado; elegí otro")
        if len(section) > self.ALIAS_MAX_LENGTH:
            raise SetupValidationError(
                f"El nombre puede tener hasta {self.ALIAS_MAX_LENGTH} letras")
        # ConfigParser no admite corchetes en el nombre de una sección, y
        # get_config_for_printer() interpreta ":" como host:puerto, "=" y "&"
        # como configuración embebida y cuatro números separados por puntos
        # como una IP: con esos nombres la impresora nunca se encontraría.
        if any(c in section for c in "[]:=&"):
            raise SetupValidationError("El nombre no puede tener [ ] : = &")
        if section.count(".") == 3:
            raise SetupValidationError("El nombre no puede ser una dirección IP")
        return section

    def suggest_alias(self, base="Impresora"):
        """Un nombre libre para proponer: "Impresora", "Impresora 2", ..."""
        existentes = {s.lower() for s in self.config.get_actual_config()}
        if base.lower() not in existentes:
            return base
        numero = 2
        while f"{base} {numero}".lower() in existentes:
            numero += 1
        return f"{base} {numero}"

    # -- escritura --------------------------------------------------------

    def save_confirmed(
        self,
        alias,
        candidate,
        technical_success=False,
        physical_confirmed=False,
    ):
        """
        Guarda la impresora. Exige las dos confirmaciones: que la prueba haya
        salido bien técnicamente Y que la persona haya visto el ticket en
        papel. Cualquier error deja el config.ini como estaba.
        """
        section = self.validate_alias(alias)
        if not technical_success or not physical_confirmed:
            raise ConfirmationRequiredError(
                "La impresora debe superar la prueba y confirmarse en papel"
            )

        current = self.config.get_actual_config()
        for existing in current:
            if existing.lower() == section.lower():
                raise DuplicatePrinterError(
                    f"Ya hay una impresora que se llama {existing}", existing_alias=existing)

        duplicate = self.find_duplicate(candidate)
        if duplicate is not None:
            raise DuplicatePrinterError(
                f"Esta impresora ya está configurada como {duplicate}",
                existing_alias=duplicate,
            )

        if not self.config.set(section, candidate.config_to_persist()):
            raise SetupPersistenceError("No se pudo guardar la impresora")
        return section


# -- Validación y huellas ----------------------------------------------------

# Parámetro sin el cual cada driver no puede imprimir.
_REQUIRED_BY_DRIVER = {
    "win32raw": ("printer_name",),
    "network": ("host",),
    "usbprint": ("idvendor", "idproduct"),
    "serial": ("devfile",),
    "usb": ("idvendor", "idproduct"),
    "bluetooth": ("mac_address",),
}


def is_valid_printer_config(values):
    """
    ¿Esta sección del config.ini describe una impresora utilizable?

    Solo se exige lo mínimo de cada driver: las impresoras que configuró el
    backend (comando `configure`) o soporte a mano también cuentan.
    """
    if not isinstance(values, dict):
        return False
    driver = str(values.get("driver", "")).strip().lower()
    if not driver:
        return False
    keys = {str(k).lower(): v for k, v in values.items()}
    if driver == "bluetooth" and keys.get("macaddress"):
        return True
    for requerido in _REQUIRED_BY_DRIVER.get(driver, ()):
        if not str(keys.get(requerido, "")).strip():
            return False
    return True


def _usb_id(value, label):
    try:
        number = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError) as error:
        raise SetupValidationError(f"El ID de {label} no es válido") from error
    if not 0 <= number <= 0xFFFF:
        raise SetupValidationError(f"El ID de {label} no es válido")
    return number


# Transportes cuya dirección identifica a UNA impresora física.
_ADDRESS_IS_IDENTITY = {"win32raw", "network", "serial"}


def _driver_fingerprint(values):
    driver = str(values.get("driver", "")).lower()
    if driver == "win32raw":
        return driver, str(values.get("printer_name", "")).casefold()
    if driver == "network":
        return (
            driver,
            str(values.get("host", "")).strip(),
            str(values.get("port", DEFAULT_RAW_PORT)).strip(),
        )
    if driver in ("usb", "usbprint"):
        return (
            driver,
            str(values.get("idVendor", "")).lower(),
            str(values.get("idProduct", "")).lower(),
            str(values.get("serial_number", "")).strip(),
        )
    if driver == "serial":
        return driver, str(values.get("devfile", "")).strip().upper()
    return None
