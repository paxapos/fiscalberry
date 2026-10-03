# coding=utf-8
"""
Servicio de configuración de impresoras del asistente (#171).

Lo que fijan estos tests:

- Cada transporte (Win32Raw, Network, UsbPrint, Serial, Usb) produce la
  configuración que su driver espera, con una identidad estable y la capacidad
  de leer el estado real cuando el transporte la tiene.
- Nada se guarda sin prueba técnica Y confirmación en papel, y una entrada
  inválida no toca config.ini.
- Una impresora no se configura dos veces, ni con otro nombre ni por otro
  camino; dos impresoras distintas del mismo modelo sí.
- El nombre elegido tiene que ser uno con el que el backend pueda imprimir.
- Ningún diagnóstico de red espera más de 3 segundos.
"""

import configparser
import socket

import pytest

from fiscalberry.common import printer_setup as ps
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


def _guardar(service, alias, candidate):
    return service.save_confirmed(alias, candidate, technical_success=True,
                                  physical_confirmed=True)


# --------------------------------------------------------------------------
# Los cinco transportes
# --------------------------------------------------------------------------

def test_cola_de_windows_va_por_win32raw_y_no_lee_estado():
    candidate = PrinterCandidate.windows_queue("EPSON Cocina", "USB001")

    assert candidate.connection == ps.WINDOWS
    assert candidate.driver_config == {"driver": "Win32Raw", "printer_name": "EPSON Cocina"}
    assert candidate.stable_id == "windows:epson cocina"
    assert candidate.detail == "USB001"
    # El spooler es unidireccional: dice "Lista" aunque esté apagada.
    assert candidate.status_readable is False


def test_red_guarda_un_timeout_corto_y_lee_estado():
    candidate = PrinterCandidate.network("192.168.1.80", "9100")

    assert candidate.driver_config == {
        "driver": "Network",
        "host": "192.168.1.80",
        "port": "9100",
        # El default de python-escpos es 60 s por ticket con la impresora apagada.
        "timeout": "10",
    }
    assert candidate.stable_id == "network:192.168.1.80:9100"
    assert candidate.status_readable is True


@pytest.mark.parametrize("host,port", [
    ("no-es-una-ip", 9100),
    ("192.168.1.80", 0),
    ("192.168.1.80", 70000),
    ("192.168.1.80", "puerto"),
    ("fe80::1", 9100),
    # No son la dirección de un equipo.
    ("0.0.0.0", 9100),
    ("224.0.0.1", 9100),
    ("255.255.255.255", 9100),
])
def test_red_rechaza_datos_invalidos(host, port):
    with pytest.raises(SetupValidationError):
        PrinterCandidate.network(host, port)


def test_usbprint_guarda_la_identidad_y_no_la_ruta():
    ruta = r"\\?\usb#vid_04b8&pid_0202#abc123#{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"
    candidate = PrinterCandidate.usbprint("04B8", "0202", serial="ABC123", device_path=ruta)

    assert candidate.connection == ps.USBPRINT
    assert candidate.driver_config == {
        "driver": "UsbPrint", "idVendor": "0x04b8", "idProduct": "0x0202",
        "serial_number": "ABC123",
    }
    # La ruta cambia al enchufarla en otro USB: con número de serie no se guarda.
    assert candidate.ubicacion == ruta
    assert ruta not in candidate.driver_config.values()
    assert candidate.stable_id == "usb:04b8:0202:ABC123"
    assert candidate.status_readable is True


def test_usbprint_sin_serie_guarda_la_ruta_para_distinguir_dos_iguales():
    ruta = r"\\?\usb#vid_0fe6&pid_811e#6&2c5b3a7&0&1#{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"
    candidate = PrinterCandidate.usbprint("0FE6", "811E", device_path=ruta)

    assert candidate.driver_config["device_path"] == ruta
    assert "serial_number" not in candidate.driver_config
    assert candidate.stable_id == "usb:0fe6:811e@" + ruta.casefold()


def test_serial_por_com_con_identidad_del_adaptador():
    candidate = PrinterCandidate.serial("COM3", vendor_id="067b", product_id="2303",
                                        serial="PL123")

    assert candidate.connection == ps.SERIAL
    assert candidate.driver_config == {"driver": "Serial", "devfile": "COM3",
                                       "baudrate": "9600"}
    assert candidate.stable_id == "serial:067b:2303:PL123"
    assert candidate.ubicacion == "COM3"
    assert candidate.status_readable is True


@pytest.mark.parametrize("port,baudrate", [("", 9600), ("COM3", "rapido"), ("COM3", 0)])
def test_serial_rechaza_datos_invalidos(port, baudrate):
    with pytest.raises(SetupValidationError):
        PrinterCandidate.serial(port, baudrate=baudrate)


def test_usb_pyusb_queda_para_winusb():
    candidate = PrinterCandidate.usb(0x04B8, "0x0202", serial="ABC123")

    assert candidate.connection == ps.USB
    assert candidate.driver_config == {
        "driver": "Usb", "idVendor": "0x04b8", "idProduct": "0x0202"}
    assert candidate.stable_id == "usb:04b8:0202:ABC123"
    assert candidate.status_readable is True


@pytest.mark.parametrize("valor,esperado", [
    ("04b8", 0x04B8), ("04B8", 0x04B8), ("0x04b8", 0x04B8), ("4b8", 0x04B8),
    (0x04B8, 0x04B8), (" 0202 ", 0x0202),
])
def test_ids_usb_se_leen_en_hexadecimal(valor, esperado):
    """Así los muestran Windows, lsusb y las etiquetas: '04B8', no '1208'."""
    candidate = PrinterCandidate.usb(valor, "0202")
    assert candidate.driver_config["idVendor"] == f"0x{esperado:04x}"


@pytest.mark.parametrize("valor", ["zz", "", "10000", -1, 0x10000, True, None])
def test_ids_usb_invalidos(valor):
    with pytest.raises(SetupValidationError):
        PrinterCandidate.usb(valor, "0202")


# --------------------------------------------------------------------------
# Diagnóstico rápido de red
# --------------------------------------------------------------------------

class ConexionFalsa:
    def __init__(self):
        self.cerrada = False

    def close(self):
        self.cerrada = True


def _conectar(resultado, registro=None):
    def conectar(destino, timeout):
        if registro is not None:
            registro.append((destino, timeout))
        if isinstance(resultado, BaseException):
            raise resultado
        return resultado
    return conectar


def test_probe_tcp_ok_cierra_la_conexion():
    conexion = ConexionFalsa()
    llamadas = []
    assert ps.probe_tcp("192.168.1.80", 9100, conectar=_conectar(conexion, llamadas)) == ps.TCP_OK
    assert conexion.cerrada
    assert llamadas == [(("192.168.1.80", 9100), 3.0)]


@pytest.mark.parametrize("error,esperado", [
    (ConnectionRefusedError(), ps.TCP_RECHAZADO),
    (socket.timeout(), ps.TCP_SIN_RESPUESTA),
    (TimeoutError(), ps.TCP_SIN_RESPUESTA),
    (OSError(113, "No route to host"), ps.TCP_SIN_RESPUESTA),
])
def test_probe_tcp_clasifica_la_falla(error, esperado):
    assert ps.probe_tcp("192.168.1.80", 9100, conectar=_conectar(error)) == esperado


@pytest.mark.parametrize("host,port", [("hola", 9100), ("192.168.1.80", 0), ("", 9100)])
def test_probe_tcp_datos_invalidos_no_intenta_conectar(host, port):
    llamadas = []
    assert ps.probe_tcp(host, port, conectar=_conectar(ConexionFalsa(), llamadas)) == ps.TCP_INVALIDO
    assert llamadas == []


def test_probe_tcp_nunca_espera_mas_de_3_segundos():
    llamadas = []
    ps.probe_tcp("192.168.1.80", 9100, timeout=60, conectar=_conectar(ConexionFalsa(), llamadas))
    assert llamadas[0][1] == 3.0


def test_probe_tcp_real_contra_un_puerto_cerrado():
    """Sin mocks: un puerto local sin nadie escuchando responde rechazado."""
    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    puerto = servidor.getsockname()[1]
    servidor.close()
    assert ps.probe_tcp("127.0.0.1", puerto, timeout=1) == ps.TCP_RECHAZADO


# --------------------------------------------------------------------------
# Nombres
# --------------------------------------------------------------------------

@pytest.mark.parametrize("alias", [
    "", "   ", "SERVIDOR", "Paxaprinter", "updater", "RabbitMq",
    # Configberry.get_config_for_printer() los interpretaría como otra cosa y
    # ningún ticket llegaría a la impresora:
    "Barra:1",           # IP:puerto
    "driver=Dummy",      # configuración en línea
    "caja.1.piso.2",     # parece una IP (tres puntos)
    "Cocina [vieja]",    # rompe la sección del INI
    "Cocina\nBarra",
])
def test_rechaza_nombres_con_los_que_no_se_podria_imprimir(alias):
    config = ConfigFalso()
    with pytest.raises(SetupValidationError):
        _guardar(PrinterSetupService(config), alias,
                 PrinterCandidate.windows_queue("Cocina", "USB001"))
    assert config.writes == []


# --------------------------------------------------------------------------
# Guardar
# --------------------------------------------------------------------------

@pytest.mark.parametrize("technical_success,physical_confirmed", [
    (False, False),
    (False, True),
    (True, False),
])
def test_no_persiste_sin_doble_confirmacion(technical_success, physical_confirmed):
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
    candidate = PrinterCandidate.network("192.168.1.80", 9100)

    assert _guardar(PrinterSetupService(config), " Barra ", candidate) == "Barra"

    assert config.writes == [(
        "Barra",
        {**candidate.driver_config, "_setup_id": candidate.stable_id},
    )]


def test_misma_impresora_con_otro_nombre_es_duplicada_y_dice_cual():
    config = ConfigFalso()
    service = PrinterSetupService(config)
    _guardar(service, "Cocina", PrinterCandidate.network("192.168.1.80", 9100))

    with pytest.raises(DuplicatePrinterError) as error:
        _guardar(service, "Barra", PrinterCandidate.network("192.168.1.80", "9100"))

    # Resultado accionable: el asistente puede decir "ya está como Cocina".
    assert error.value.existente == "Cocina"
    assert "Cocina" in str(error.value)
    assert [s for s, _ in config.writes] == ["Cocina"]


def test_nombre_repetido_aunque_cambien_las_mayusculas():
    config = ConfigFalso()
    service = PrinterSetupService(config)
    _guardar(service, "Cocina", PrinterCandidate.network("192.168.1.80", 9100))

    with pytest.raises(DuplicatePrinterError):
        _guardar(service, "COCINA", PrinterCandidate.network("192.168.1.81", 9100))


def test_cola_de_windows_no_distingue_mayusculas():
    config = ConfigFalso()
    service = PrinterSetupService(config)
    _guardar(service, "Cocina", PrinterCandidate.windows_queue("EPSON TM-T20"))

    with pytest.raises(DuplicatePrinterError):
        _guardar(service, "Barra", PrinterCandidate.windows_queue("epson tm-t20"))


def test_impresora_guardada_antes_del_asistente_tambien_cuenta():
    config = ConfigFalso({
        "Cocina": {"driver": "Network", "host": "192.168.1.80", "port": "9100"},
        "Barra": {"driver": "Win32Raw", "printer_name": "EPSON Barra"},
    })
    service = PrinterSetupService(config)

    with pytest.raises(DuplicatePrinterError) as error:
        _guardar(service, "Nueva", PrinterCandidate.network("192.168.1.80", 9100))
    assert error.value.existente == "Cocina"
    with pytest.raises(DuplicatePrinterError):
        _guardar(service, "Nueva", PrinterCandidate.windows_queue("epson barra"))
    assert config.writes == []


def test_mismo_usb_por_usbprint_y_por_pyusb_es_la_misma_impresora():
    config = ConfigFalso()
    service = PrinterSetupService(config)
    _guardar(service, "Cocina", PrinterCandidate.usbprint("04b8", "0202", serial="ABC"))

    with pytest.raises(DuplicatePrinterError):
        _guardar(service, "Barra", PrinterCandidate.usb(0x04B8, 0x0202, serial="ABC"))


def test_permite_mismo_modelo_usb_con_series_distintas():
    config = ConfigFalso()
    service = PrinterSetupService(config)

    _guardar(service, "Cocina", PrinterCandidate.usb(0x04B8, 0x0202, serial="SERIE-A"))
    _guardar(service, "Barra", PrinterCandidate.usb(0x04B8, 0x0202, serial="SERIE-B"))

    assert [section for section, _values in config.writes] == ["Cocina", "Barra"]


def test_dos_impresoras_iguales_sin_serie_se_distinguen_por_donde_estan():
    """Cocina y barra del mismo modelo barato, que no informa número de serie."""
    config = ConfigFalso()
    service = PrinterSetupService(config)

    _guardar(service, "Cocina", PrinterCandidate.usbprint("0416", "5011", device_path=r"\\?\usb#1"))
    _guardar(service, "Barra", PrinterCandidate.usbprint("0416", "5011", device_path=r"\\?\usb#2"))
    with pytest.raises(DuplicatePrinterError):
        _guardar(service, "Otra", PrinterCandidate.usbprint("0416", "5011", device_path=r"\\?\USB#1"))


def test_dos_adaptadores_com_sin_serie_no_chocan():
    """Los CH340 no tienen número de serie: dos iguales se distinguen por el COM."""
    config = ConfigFalso()
    service = PrinterSetupService(config)

    _guardar(service, "Cocina", PrinterCandidate.serial("COM3", "1a86", "7523"))
    _guardar(service, "Barra", PrinterCandidate.serial("COM4", "1a86", "7523"))
    with pytest.raises(DuplicatePrinterError):
        _guardar(service, "Otra", PrinterCandidate.serial("com3"))


def test_adaptador_com_con_serie_se_reconoce_aunque_cambie_de_puerto():
    config = ConfigFalso()
    service = PrinterSetupService(config)
    _guardar(service, "Cocina", PrinterCandidate.serial("COM3", "0403", "6001", serial="FT1"))

    with pytest.raises(DuplicatePrinterError):
        _guardar(service, "Barra", PrinterCandidate.serial("COM7", "0403", "6001", serial="FT1"))


def test_las_secciones_reservadas_no_cuentan_como_impresoras():
    config = ConfigFalso({
        "SERVIDOR": {"uuid": "x", "sio_host": "https://beta.paxapos.com"},
        "Paxaprinter": {"tenant": "demo"},
    })
    _guardar(PrinterSetupService(config), "Cocina", PrinterCandidate.windows_queue("Cocina"))
    assert [s for s, _ in config.writes] == ["Cocina"]


def test_si_no_se_puede_escribir_lo_dice():
    class ConfigQueFalla(ConfigFalso):
        def set(self, section, values):
            return False

    with pytest.raises(ps.SetupPersistenceError):
        _guardar(PrinterSetupService(ConfigQueFalla()), "Cocina",
                 PrinterCandidate.windows_queue("Cocina"))


# --------------------------------------------------------------------------
# Con Configberry de verdad sobre un config.ini temporal
# --------------------------------------------------------------------------

@pytest.fixture
def config_real(tmp_path, monkeypatch):
    from fiscalberry.common.Configberry import Configberry

    ini = tmp_path / "config.ini"
    ini.write_text(
        "[SERVIDOR]\nuuid = abc-123\nsio_host = https://beta.paxapos.com\n\n"
        "[Paxaprinter]\ntenant = demo\n\n"
        "[Vieja]\ndriver = Network\nhost = 192.168.1.50\nport = 9100\n",
        encoding="utf-8",
    )
    cfg = Configberry()
    parser = configparser.ConfigParser()
    parser.optionxform = str
    monkeypatch.setattr(Configberry, "config", parser)
    monkeypatch.setattr(Configberry, "_loaded", False)
    monkeypatch.setattr(cfg, "configFilePath", str(ini))
    monkeypatch.setattr(cfg, "_listeners", [])
    return cfg, ini


def test_guarda_en_config_ini_y_el_backend_la_encuentra(config_real):
    cfg, ini = config_real
    candidate = PrinterCandidate.network("192.168.1.80", 9100)

    _guardar(PrinterSetupService(cfg), "Barra", candidate)

    leido = configparser.ConfigParser()
    leido.optionxform = str
    leido.read(ini)
    assert dict(leido["Barra"]) == {**candidate.driver_config, "_setup_id": candidate.stable_id}
    # El mismo camino que usa ComandosHandler para cada ticket.
    assert cfg.get_config_for_printer("Barra")["host"] == "192.168.1.80"


def test_entradas_invalidas_no_modifican_config_ini(config_real):
    cfg, ini = config_real
    antes = ini.read_bytes()
    service = PrinterSetupService(cfg)

    for alias, candidate, kwargs in [
        ("Barra:1", PrinterCandidate.network("192.168.1.80"), {}),
        ("Barra", PrinterCandidate.network("192.168.1.50"), {}),   # duplicada de "Vieja"
        ("Barra", PrinterCandidate.network("192.168.1.81"), {"physical_confirmed": False}),
    ]:
        with pytest.raises(SetupValidationError):
            service.save_confirmed(alias, candidate, technical_success=True,
                                   physical_confirmed=kwargs.get("physical_confirmed", True))

    assert ini.read_bytes() == antes


def test_ve_lo_que_otro_proceso_escribio_en_el_archivo(config_real):
    """La adopción o el otro proceso de Android también escriben config.ini."""
    import os

    cfg, ini = config_real
    assert "Cocina" not in cfg.get_actual_config()

    with open(ini, "a", encoding="utf-8") as fh:
        fh.write("\n[Cocina]\ndriver = Win32Raw\nprinter_name = EPSON\n")
    futuro = os.path.getmtime(ini) + 5
    os.utime(ini, (futuro, futuro))

    with pytest.raises(DuplicatePrinterError):
        _guardar(PrinterSetupService(cfg), "Otra", PrinterCandidate.windows_queue("epson"))


@pytest.mark.parametrize("alias", ["Barra:1", "driver=Dummy", "caja.1.piso.2"])
def test_la_regla_de_nombres_es_la_del_backend(config_real, alias):
    """
    Por qué se rechazan esos nombres: aunque la sección exista en config.ini,
    get_config_for_printer() (el camino de cada ticket) nunca la devuelve.
    """
    cfg, ini = config_real
    with open(ini, "a", encoding="utf-8") as fh:
        fh.write(f"\n[{alias}]\ndriver = Dummy\norigen = seccion\n")

    assert cfg.get_config_for_printer(alias).get("origen") != "seccion"
    with pytest.raises(SetupValidationError):
        ps.validar_nombre(alias)


@pytest.mark.parametrize("alias", ["Cocina", "Barra 2", "Caja-1", "Impresora.Fiscal"])
def test_los_nombres_aceptados_los_resuelve_el_backend(config_real, alias):
    cfg, _ini = config_real
    _guardar(PrinterSetupService(cfg), alias, PrinterCandidate.windows_queue(f"Cola {alias}"))
    assert cfg.get_config_for_printer(alias)["printer_name"] == f"Cola {alias}"
