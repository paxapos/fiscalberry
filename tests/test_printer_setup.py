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
        # El default de python-escpos es 60 s por ticket con la impresora apagada.
        "timeout": "10",
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

# ---------------------------------------------------------------------------
# #171: los cinco transportes y sus capacidades
# ---------------------------------------------------------------------------

import configparser  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402

from fiscalberry.common import printer_setup as ps  # noqa: E402


def test_solo_los_transportes_bidireccionales_leen_estado():
    """DLE EOT necesita ida y vuelta: por el spooler de Windows no hay vuelta."""
    assert not PrinterCandidate.windows_queue("Cocina").status_readable
    assert PrinterCandidate.network("192.168.1.80").status_readable
    assert PrinterCandidate.usbprint(r"\\?\usb#vid_04b8", 0x04B8, 0x0202, "X").status_readable
    assert PrinterCandidate.serial("COM3").status_readable
    assert PrinterCandidate.usb(0x04B8, 0x0202).status_readable


@pytest.mark.parametrize("candidato,transporte", [
    (lambda: PrinterCandidate.windows_queue("Cocina", "USB001"), ps.TRANSPORT_WIN32RAW),
    (lambda: PrinterCandidate.network("192.168.1.80"), ps.TRANSPORT_NETWORK),
    (lambda: PrinterCandidate.usbprint("ruta", 1, 2, "S"), ps.TRANSPORT_USBPRINT),
    (lambda: PrinterCandidate.serial("COM3"), ps.TRANSPORT_SERIAL),
    (lambda: PrinterCandidate.usb(1, 2), ps.TRANSPORT_USB),
])
def test_el_transporte_coincide_con_el_driver(candidato, transporte):
    candidate = candidato()
    assert candidate.transport == transporte
    assert candidate.driver_config["driver"] == transporte


def test_usbprint_guarda_la_identidad_y_no_la_ruta():
    """La ruta incluye el puerto USB físico: cambia si se enchufa en otro."""
    ruta = r"\\?\usb#vid_04b8&pid_0202#abc123#{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"
    candidate = PrinterCandidate.usbprint(ruta, "0x04B8", 0x0202, serial="ABC123")

    # Para la prueba sí se usa la ruta...
    assert candidate.driver_config["device_path"] == ruta
    # ...pero lo que se guarda es VID/PID/serie.
    assert candidate.config_to_persist() == {
        "driver": "UsbPrint",
        "idVendor": "0x04b8",
        "idProduct": "0x0202",
        "serial_number": "ABC123",
        "_setup_id": "usbprint:04b8:0202:ABC123",
    }


def test_usbprint_sin_numero_de_serie_depende_del_puerto():
    a = PrinterCandidate.usbprint("RUTA-PUERTO-1", 0x0416, 0x5011)
    b = PrinterCandidate.usbprint("RUTA-PUERTO-2", 0x0416, 0x5011)

    # Dos térmicas iguales sin serie solo se distinguen por dónde están.
    assert a.stable_id != b.stable_id
    assert a.config_to_persist()["device_path"] == "RUTA-PUERTO-1"


def test_usbprint_exige_ruta_e_ids_validos():
    with pytest.raises(SetupValidationError):
        PrinterCandidate.usbprint("", 1, 2)
    with pytest.raises(SetupValidationError):
        PrinterCandidate.usbprint("ruta", "no-es-hex", 2)


def test_serial_normaliza_el_puerto_y_guarda_el_usb_como_metadata():
    candidate = PrinterCandidate.serial("com4", 115200, vendor_id=0x1A86,
                                        product_id=0x7523, serial_number="")

    assert candidate.driver_config == {
        "driver": "Serial",
        "devfile": "COM4",
        "baudrate": "115200",
        "_usb_vid": "0x1a86",
        "_usb_pid": "0x7523",
    }
    assert candidate.stable_id == "serial:1a86:7523@COM4"
    assert candidate.connection_label == "Puerto serie (COM4)"


def test_serial_con_numero_de_serie_sobrevive_al_cambio_de_com():
    antes = PrinterCandidate.serial("COM3", vendor_id=0x0403, product_id=0x6001,
                                    serial_number="FT123")
    despues = PrinterCandidate.serial("COM7", vendor_id=0x0403, product_id=0x6001,
                                      serial_number="FT123")
    assert antes.stable_id == despues.stable_id == "serial:0403:6001:FT123"


@pytest.mark.parametrize("puerto,baudios", [("", 9600), ("COM3", "rápido"), ("COM3", 0)])
def test_serial_rechaza_datos_invalidos(puerto, baudios):
    with pytest.raises(SetupValidationError):
        PrinterCandidate.serial(puerto, baudios)


def test_etiqueta_de_conexion_para_el_ticket_de_prueba():
    assert PrinterCandidate.network("192.168.1.80").connection_label == "Red (192.168.1.80)"
    assert (PrinterCandidate.network("192.168.1.80", 9101).connection_label
            == "Red (192.168.1.80:9101)")
    assert (PrinterCandidate.windows_queue("EPSON", "USB001").connection_label
            == "Cola de Windows (USB001)")


@pytest.mark.parametrize("host", ["0.0.0.0", "224.0.0.1", "255.255.255.255", "::1", "impresora.local"])
def test_red_rechaza_direcciones_que_no_pueden_ser_una_impresora(host):
    with pytest.raises(SetupValidationError):
        PrinterCandidate.network(host)


# ---------------------------------------------------------------------------
# Duplicados: resultado accionable
# ---------------------------------------------------------------------------

def _guardar(service, alias, candidate):
    return service.save_confirmed(alias, candidate, technical_success=True,
                                  physical_confirmed=True)


def test_el_duplicado_dice_con_que_nombre_esta_guardada():
    config = ConfigFalso()
    service = PrinterSetupService(config)
    _guardar(service, "Cocina", PrinterCandidate.windows_queue("EPSON TM-T20"))

    with pytest.raises(DuplicatePrinterError) as error:
        _guardar(service, "Barra", PrinterCandidate.windows_queue("epson tm-t20"))

    assert error.value.existing_alias == "Cocina"
    assert "Cocina" in str(error.value)
    assert [s for s, _ in config.writes] == ["Cocina"]


def test_find_duplicate_antes_de_probar():
    config = ConfigFalso({"Caja": {"driver": "Serial", "devfile": "com3"}})
    service = PrinterSetupService(config)

    assert service.find_duplicate(PrinterCandidate.serial("COM3")) == "Caja"
    assert service.find_duplicate(PrinterCandidate.serial("COM4")) is None


def test_el_nombre_repetido_no_distingue_mayusculas():
    config = ConfigFalso()
    service = PrinterSetupService(config)
    _guardar(service, "Cocina", PrinterCandidate.network("192.168.1.80"))

    with pytest.raises(DuplicatePrinterError) as error:
        _guardar(service, "cocina", PrinterCandidate.network("192.168.1.81"))
    assert error.value.existing_alias == "Cocina"


def test_misma_usbprint_en_otro_puerto_es_duplicada():
    config = ConfigFalso()
    service = PrinterSetupService(config)
    _guardar(service, "Cocina", PrinterCandidate.usbprint("PUERTO-1", 0x04B8, 0x0202, "S1"))

    with pytest.raises(DuplicatePrinterError):
        _guardar(service, "Barra", PrinterCandidate.usbprint("PUERTO-2", 0x04B8, 0x0202, "S1"))


# ---------------------------------------------------------------------------
# Nombres
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("alias", [
    "192.168.1.50",      # get_config_for_printer lo trataría como IP
    "Caja:1",            # ...como host:puerto
    "driver=Network",    # ...como configuración embebida
    "a&b",
    "[Cocina]",
    "Updater",           # sección del auto-actualizador
    "x" * 41,
])
def test_nombres_que_romperian_la_busqueda_de_la_impresora(alias):
    config = ConfigFalso()
    with pytest.raises(SetupValidationError):
        _guardar(PrinterSetupService(config), alias, PrinterCandidate.network("192.168.1.80"))
    assert config.writes == []


def test_el_nombre_se_normaliza():
    service = PrinterSetupService(ConfigFalso())
    assert service.validate_alias("  Barra   de   tragos ") == "Barra de tragos"


def test_sugiere_un_nombre_libre():
    service = PrinterSetupService(ConfigFalso({
        "SERVIDOR": {"uuid": "x"},
        "Impresora": {"driver": "Dummy"},
        "Impresora 2": {"driver": "Dummy"},
    }))
    assert service.suggest_alias() == "Impresora 3"
    assert PrinterSetupService(ConfigFalso()).suggest_alias() == "Impresora"


# ---------------------------------------------------------------------------
# Impresoras configuradas (lo usa el asistente para saber si hace falta)
# ---------------------------------------------------------------------------

def test_impresoras_configuradas_ignora_secciones_que_no_son_impresoras():
    service = PrinterSetupService(ConfigFalso({
        "SERVIDOR": {"uuid": "x", "sio_host": "https://x"},
        "Paxaprinter": {"tenant": "t"},
        "Updater": {"enabled": "true"},
        "Cocina": {"driver": "Network", "host": "192.168.1.80"},
        "Rota": {"driver": "Network"},                 # sin host: no sirve
        "Vieja": {"host": "192.168.1.2"},              # sin driver
        "Caja": {"driver": "Win32Raw", "printer_name": "EPSON"},
    }))

    assert sorted(service.configured_printers()) == ["Caja", "Cocina"]
    assert service.has_configured_printers()
    assert not PrinterSetupService(ConfigFalso({"SERVIDOR": {}})).has_configured_printers()


# ---------------------------------------------------------------------------
# probe_tcp: diagnóstico rápido, nunca más de 3 s
# ---------------------------------------------------------------------------

class SocketFalso:
    def __init__(self, resultado=None):
        self.resultado = resultado
        self.timeout = None
        self.destino = None
        self.cerrado = False

    def settimeout(self, valor):
        self.timeout = valor

    def connect(self, destino):
        self.destino = destino
        if self.resultado is not None:
            raise self.resultado

    def close(self):
        self.cerrado = True


@pytest.mark.parametrize("error,esperado", [
    (None, ps.TCP_OK),
    (ConnectionRefusedError(), ps.TCP_REFUSED),
    (socket.timeout("timed out"), ps.TCP_NO_RESPONSE),
    (OSError(113, "No route to host"), ps.TCP_NO_RESPONSE),
])
def test_probe_tcp_clasifica_la_respuesta(error, esperado):
    falso = SocketFalso(error)

    assert ps.probe_tcp("192.168.1.80", 9100, socket_factory=lambda: falso) == esperado
    assert falso.destino == ("192.168.1.80", 9100)
    assert falso.cerrado


@pytest.mark.parametrize("pedido", [0, -1, 60, "no", None, 10])
def test_probe_tcp_nunca_espera_mas_de_tres_segundos(pedido):
    falso = SocketFalso()
    ps.probe_tcp("192.168.1.80", timeout=pedido, socket_factory=lambda: falso)
    assert 0 < falso.timeout <= ps.MAX_PROBE_TIMEOUT


@pytest.mark.parametrize("host,port", [("no-es-ip", 9100), ("192.168.1.80", 0),
                                       ("192.168.1.80", "abc"), ("", 9100)])
def test_probe_tcp_con_datos_invalidos_no_intenta_conectar(host, port):
    def no_crear():
        pytest.fail("no debe abrir un socket con datos inválidos")

    assert ps.probe_tcp(host, port, socket_factory=no_crear) == ps.TCP_INVALID


def test_probe_tcp_contra_un_puerto_real():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    puerto = servidor.getsockname()[1]
    try:
        assert ps.probe_tcp("127.0.0.1", puerto, timeout=1) == ps.TCP_OK
    finally:
        servidor.close()
    # Mismo puerto, ya cerrado: el equipo responde que no hay nadie.
    assert ps.probe_tcp("127.0.0.1", puerto, timeout=1) == ps.TCP_REFUSED


# ---------------------------------------------------------------------------
# Con el Configberry real: escritura atómica y nada escrito ante errores
# ---------------------------------------------------------------------------

@pytest.fixture
def configberry_real(monkeypatch, tmp_path):
    from fiscalberry.common.Configberry import Configberry

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # El ConfigParser es un atributo de clase: uno limpio para no arrastrar
    # secciones de otros tests (read() fusiona, nunca borra).
    limpio = configparser.ConfigParser()
    limpio.optionxform = str
    monkeypatch.setattr(Configberry, "config", limpio)
    monkeypatch.setattr(Configberry, "_instance", None)
    c = Configberry()
    yield c
    Configberry._instance = None


def test_persiste_en_el_config_ini_real(configberry_real):
    service = PrinterSetupService(configberry_real)
    candidate = PrinterCandidate.network("192.168.1.80")

    _guardar(service, "Barra", candidate)

    releido = configparser.ConfigParser()
    releido.optionxform = str
    releido.read(configberry_real.getConfigFIle())
    assert dict(releido["Barra"]) == candidate.config_to_persist()
    # Y la busca bien el camino de impresión.
    assert configberry_real.get_config_for_printer("Barra")["host"] == "192.168.1.80"


@pytest.mark.parametrize("alias,confirmado", [
    ("", True),                 # nombre inválido
    ("Barra", False),           # sin confirmación en papel
    ("SERVIDOR", True),         # reservado
])
def test_entradas_invalidas_no_tocan_el_config_ini(configberry_real, alias, confirmado):
    ruta = configberry_real.getConfigFIle()
    antes = open(ruta, "rb").read()

    with pytest.raises(SetupValidationError):
        PrinterSetupService(configberry_real).save_confirmed(
            alias, PrinterCandidate.network("192.168.1.80"),
            technical_success=True, physical_confirmed=confirmado)

    assert open(ruta, "rb").read() == antes


def test_si_la_escritura_falla_el_config_queda_como_estaba(configberry_real, monkeypatch):
    ruta = configberry_real.getConfigFIle()
    antes = open(ruta, "rb").read()
    real_replace = os.replace

    def replace_que_falla(src, dst):
        if str(dst) == str(ruta):
            raise OSError("disco lleno")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace_que_falla)

    with pytest.raises(ps.SetupPersistenceError):
        _guardar(PrinterSetupService(configberry_real), "Barra",
                 PrinterCandidate.network("192.168.1.80"))

    assert open(ruta, "rb").read() == antes
