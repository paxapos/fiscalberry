# coding=utf-8
import pytest

from fiscalberry.common.printer_setup import (
    ConfirmationRequiredError,
    DuplicatePrinterError,
    PrinterCandidate,
    PrinterSetupService,
    SetupValidationError,
)


class ConfigFalso:
    def __init__(self, data=None):
        self.data = data or {}
        self.writes = []

    def get_actual_config(self):
        return {section: dict(values) for section, values in self.data.items()}

    def set(self, section, values):
        self.writes.append((section, dict(values)))
        self.data[section] = dict(values)
        return True


def test_candidato_windows_genera_config_win32raw():
    candidate = PrinterCandidate.windows_queue("EPSON Cocina", "USB001")

    assert candidate.connection == "windows"
    assert candidate.driver_config == {
        "driver": "Win32Raw",
        "printer_name": "EPSON Cocina",
    }
    assert candidate.stable_id == "windows:EPSON Cocina"


def test_candidato_red_valida_y_normaliza_direccion():
    candidate = PrinterCandidate.network("192.168.1.80", "9100")

    assert candidate.driver_config == {
        "driver": "Network",
        "host": "192.168.1.80",
        "port": "9100",
    }
    assert candidate.stable_id == "network:192.168.1.80:9100"


@pytest.mark.parametrize("host,port", [
    ("no-es-una-ip", 9100),
    ("192.168.1.80", 0),
    ("192.168.1.80", 70000),
])
def test_candidato_red_rechaza_datos_invalidos(host, port):
    with pytest.raises(SetupValidationError):
        PrinterCandidate.network(host, port)


def test_candidato_usb_normaliza_ids_hexadecimales():
    candidate = PrinterCandidate.usb(0x04B8, "0x0202", serial="ABC123")

    assert candidate.driver_config == {
        "driver": "Usb",
        "idVendor": "0x04b8",
        "idProduct": "0x0202",
    }
    assert candidate.stable_id == "usb:04b8:0202:ABC123"


@pytest.mark.parametrize("technical_success,physical_confirmed", [
    (False, False),
    (False, True),
    (True, False),
])
def test_no_persiste_sin_doble_confirmacion(
    technical_success, physical_confirmed
):
    config = ConfigFalso()
    service = PrinterSetupService(config)
    candidate = PrinterCandidate.windows_queue("Cocina", "USB001")

    with pytest.raises(ConfirmationRequiredError):
        service.save_confirmed(
            "Cocina",
            candidate,
            technical_success=technical_success,
            physical_confirmed=physical_confirmed,
        )

    assert config.writes == []


def test_persiste_configuracion_confirmada():
    config = ConfigFalso()
    service = PrinterSetupService(config)
    candidate = PrinterCandidate.network("192.168.1.80", 9100)

    service.save_confirmed(
        "Barra",
        candidate,
        technical_success=True,
        physical_confirmed=True,
    )

    assert config.writes == [(
        "Barra",
        {**candidate.driver_config, "_setup_id": candidate.stable_id},
    )]


def test_rechaza_impresora_duplicada_sin_escribir():
    config = ConfigFalso({
        "Cocina": {
            "driver": "Network",
            "host": "192.168.1.80",
            "port": "9100",
        },
    })
    service = PrinterSetupService(config)
    candidate = PrinterCandidate.network("192.168.1.80", 9100)

    with pytest.raises(DuplicatePrinterError):
        service.save_confirmed(
            "Barra",
            candidate,
            technical_success=True,
            physical_confirmed=True,
        )

    assert config.writes == []


def test_permite_mismo_modelo_usb_con_series_distintas():
    config = ConfigFalso()
    service = PrinterSetupService(config)

    service.save_confirmed(
        "Cocina",
        PrinterCandidate.usb(0x04B8, 0x0202, serial="SERIE-A"),
        technical_success=True,
        physical_confirmed=True,
    )
    service.save_confirmed(
        "Barra",
        PrinterCandidate.usb(0x04B8, 0x0202, serial="SERIE-B"),
        technical_success=True,
        physical_confirmed=True,
    )

    assert [section for section, _values in config.writes] == ["Cocina", "Barra"]


@pytest.mark.parametrize("alias", ["", "   ", "SERVIDOR", "Paxaprinter"])
def test_rechaza_alias_vacio_o_reservado(alias):
    service = PrinterSetupService(ConfigFalso())

    with pytest.raises(SetupValidationError):
        service.save_confirmed(
            alias,
            PrinterCandidate.windows_queue("Cocina", "USB001"),
            technical_success=True,
            physical_confirmed=True,
        )