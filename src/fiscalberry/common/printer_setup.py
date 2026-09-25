from dataclasses import dataclass
import ipaddress


class SetupValidationError(ValueError):
    pass


class ConfirmationRequiredError(SetupValidationError):
    pass


class DuplicatePrinterError(SetupValidationError):
    pass


class SetupPersistenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class PrinterCandidate:
    display_name: str
    connection: str
    stable_id: str
    driver_config: dict
    detail: str = ""

    @classmethod
    def windows_queue(cls, printer_name, port_name=""):
        name = str(printer_name).strip()
        if not name:
            raise SetupValidationError("La cola de Windows no tiene nombre")
        return cls(
            display_name=name,
            connection="windows",
            stable_id=f"windows:{name}",
            driver_config={"driver": "Win32Raw", "printer_name": name},
            detail=str(port_name).strip(),
        )

    @classmethod
    def network(cls, host, port=9100):
        host_value = str(host).strip()
        try:
            address = ipaddress.ip_address(host_value)
        except ValueError as error:
            raise SetupValidationError("Ingresá una dirección IP válida") from error
        if address.version != 4:
            raise SetupValidationError("Por ahora se admite únicamente IPv4")

        try:
            port_value = int(port)
        except (TypeError, ValueError) as error:
            raise SetupValidationError("El puerto debe ser un número") from error
        if not 1 <= port_value <= 65535:
            raise SetupValidationError("El puerto debe estar entre 1 y 65535")

        host_normalized = str(address)
        return cls(
            display_name=host_normalized,
            connection="network",
            stable_id=f"network:{host_normalized}:{port_value}",
            driver_config={
                "driver": "Network",
                "host": host_normalized,
                "port": str(port_value),
            },
            detail=f"Puerto {port_value}",
        )

    @classmethod
    def usb(cls, vendor_id, product_id, serial=""):
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
                "driver": "Usb",
                "idVendor": f"0x{vendor:04x}",
                "idProduct": f"0x{product:04x}",
            },
            detail=serial_value,
        )


class PrinterSetupService:
    RESERVED_SECTIONS = {
        "servidor",
        "paxaprinter",
        "rabbitmq",
        "heartbeat",
    }

    def __init__(self, config):
        self.config = config

    def save_confirmed(
        self,
        alias,
        candidate,
        technical_success=False,
        physical_confirmed=False,
    ):
        section = str(alias).strip()
        if not section or section.lower() in self.RESERVED_SECTIONS:
            raise SetupValidationError("Elegí un nombre válido para la impresora")
        if not technical_success or not physical_confirmed:
            raise ConfirmationRequiredError(
                "La impresora debe superar la prueba y confirmarse en papel"
            )

        current = self.config.get_actual_config()
        if section in current:
            raise DuplicatePrinterError("Ya existe una impresora con ese nombre")

        values_to_save = dict(candidate.driver_config)
        values_to_save["_setup_id"] = candidate.stable_id
        fingerprint = _config_fingerprint(values_to_save)
        legacy_fingerprint = _driver_fingerprint(values_to_save)
        for values in current.values():
            current_fingerprint = _config_fingerprint(values)
            if current_fingerprint == fingerprint:
                raise DuplicatePrinterError("Esta impresora ya está configurada")
            if not values.get("_setup_id") and (
                _driver_fingerprint(values) == legacy_fingerprint
            ):
                raise DuplicatePrinterError("Esta impresora ya está configurada")

        if not self.config.set(section, values_to_save):
            raise SetupPersistenceError("No se pudo guardar la impresora")
        return section


def _usb_id(value, label):
    try:
        number = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError) as error:
        raise SetupValidationError(f"El ID de {label} no es válido") from error
    if not 0 <= number <= 0xFFFF:
        raise SetupValidationError(f"El ID de {label} no es válido")
    return number


def _config_fingerprint(values):
    setup_id = str(values.get("_setup_id", "")).strip()
    if setup_id:
        return "setup", setup_id
    return _driver_fingerprint(values)


def _driver_fingerprint(values):
    driver = str(values.get("driver", "")).lower()
    if driver == "win32raw":
        return driver, str(values.get("printer_name", "")).casefold()
    if driver == "network":
        return (
            driver,
            str(values.get("host", "")).strip(),
            str(values.get("port", "9100")).strip(),
        )
    if driver == "usb":
        return (
            driver,
            str(values.get("idVendor", "")).lower(),
            str(values.get("idProduct", "")).lower(),
        )
    return None