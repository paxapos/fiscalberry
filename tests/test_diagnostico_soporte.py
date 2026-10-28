# coding=utf-8
"""
Diagnóstico para soporte (#185).

- Snapshots aprobados del reporte en el éxito y en las fallas principales
  (tests/snapshots/diagnostico_*.txt). Si un cambio es a propósito, se
  regeneran con FISCALBERRY_UPDATE_SNAPSHOTS=1 y se revisa el diff.
- Ningún nombre de clave sensible ni su valor aparecen, aunque estén en el
  config.ini o en el registro.
- El reporte dice el paso exacto donde falló.
"""

import os
from datetime import datetime

import pytest

from fiscalberry.common import network_discovery as nd
from fiscalberry.common import printer_search as ps
from fiscalberry.common import printer_wizard as pw
from fiscalberry.common import support_report as sr
from fiscalberry.common import ticket_prueba as tp
from fiscalberry.common.printer_setup import PrinterSetupService, TCP_OK, TCP_SIN_RESPUESTA
from fiscalberry.common.usb_discovery import UsbPrintDevice, UsbSearchResult
from fiscalberry.common.windows_queues import ERROR_NO_WINDOWS, ResultadoListado, clasificar

SNAPSHOTS = os.path.join(os.path.dirname(__file__), "snapshots")

GUID = "{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"
PC = nd.NetworkAdapter(name="Ethernet", address="192.168.1.27", prefix=24,
                       gateways=("192.168.1.1",), dhcp=True, mac="A4:BB:6D:11:22:33",
                       description="Intel(R) Ethernet")
VPN = nd.NetworkAdapter(name="VPN Oficina", address="10.8.0.6", prefix=24, kind=nd.ADAPTER_VPN,
                        dhcp=False)

SECRETOS = {
    "SERVIDOR": {"uuid": "3f9a1c2e-77aa-4b1c-9d0e-5c6f7a8b9c0d",
                 "sio_host": "https://beta.paxapos.com",
                 "sio_password": "S10-Clave-Secreta",
                 "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwaXp6YSJ9.c2VjcmV0b19maXJtYQ"},
    "Paxaprinter": {"tenant": "pizzeria-don-pepe", "site_name": "Pizzeria Don Pepe",
                    "alias": "Don Pepe", "token": "tok_9f8e7d6c5b4a"},
    "RabbitMq": {"host": "mqtt.paxapos.com", "user": "mqtt-usuario-7788",
                 "mqtt_password": "MqttPass-4455", "vhost": "/"},
    "Caja": {"driver": "Win32Raw", "printer_name": "EPSON TM-T20II Receipt",
             "_setup_id": "windows:epson tm-t20ii receipt", "api_key": "k3y-super-privada"},
}
VALORES_SECRETOS = ["S10-Clave-Secreta", "eyJhbGciOiJIUzI1NiJ9", "tok_9f8e7d6c5b4a",
                    "mqtt-usuario-7788", "MqttPass-4455", "k3y-super-privada",
                    "3f9a1c2e-77aa-4b1c-9d0e", "pizzeria-don-pepe"]
CLAVES_SECRETAS = ["sio_password", "jwt", "token", "mqtt_password", "api_key", "user =", "tenant"]

LOG = [
    "2026-09-25 14:29:58 [app:1] WARNING Asistente.Prueba: Prueba fallida (tapa_abierta): "
    "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwaXp6YSJ9.c2VjcmV0b19maXJtYQ",
    "2026-09-25 14:29:59 [app:1] ERROR PrinterSearch: password=MqttPass-4455 no debería estar acá",
]


class ConfigFalso:
    def __init__(self, data):
        self.data = {k: dict(v) for k, v in data.items()}

    def get_actual_config(self):
        return {s: dict(v) for s, v in self.data.items()}

    def set(self, section, values):
        self.data[section] = dict(values)
        return True


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        self.t += 0.4
        return self.t


class TrabajoFalso:
    def cancelar(self):
        return True


def asistente(red=None, usb=None, colas=None, prueba=None, probe=lambda h, p: TCP_OK):
    config = ConfigFalso(SECRETOS)
    servicio = PrinterSetupService(config)

    def buscar(cancel=None, on_partial=None):
        r = ps.PrinterSearch(
            servicio,
            network=lambda cancel=None: red or nd.NetworkSearchResult(adapters=[PC, VPN]),
            usb=lambda cancel=None: usb or UsbSearchResult(),
            queues=lambda cancel=None: colas or ResultadoListado(error=ERROR_NO_WINDOWS),
        ).run(cancel=cancel)
        r.seconds = 2.6
        return r

    def imprimir(candidato, alias, comercio, codigo):
        if callable(prueba):
            return prueba(codigo)
        return prueba or tp.ResultadoPrueba(exito_tecnico=True, codigo=codigo)

    w = pw.PrinterWizard(servicio, commerce="Pizzeria Don Pepe", search=buscar, probe=probe,
                         print_test=imprimir, list_adapters=lambda: [PC, VPN], clock=Reloj(),
                         new_code=lambda: "K7QX")
    return w, config


def reporte(w, config):
    return sr.build_report(
        w, config.get_actual_config(), now=datetime(2026, 9, 25, 14, 30, 0), version="3.9.9",
        installation="windows-installer", system="Windows 11 (build 22631), AMD64",
        service="conectado al servidor (MQTT: sí)", log_lines=LOG, adapters=[PC, VPN])


def red_con(*hosts):
    return nd.NetworkSearchResult(
        adapters=[PC, VPN], swept=255, seconds=2.5,
        notes=["Se ignoró la conexión VPN \"VPN Oficina\"."],
        printers=[nd.NetworkPrinter(host=h, adapter=PC, model="TM-T88V", mac="00:26:AB:12:34:56")
                  for h in hosts])


def caso_exito_red():
    w, config = asistente(red=red_con("192.168.1.60"))
    w.search()
    w.choose_found("network:192.168.1.60:9100")
    w.confirm_paper(True)
    w.save("Cocina")
    return w, config


def caso_usb_tapa_abierta():
    usb = UsbSearchResult(usbprint=[UsbPrintDevice(
        r"\\?\usb#vid_04b8&pid_0e15#X4TK001234#" + GUID, 0x04B8, 0x0E15, "X4TK001234", "USB001",
        ieee1284={"MFG": "EPSON", "MDL": "TM-T20II"})])
    tapa = tp.EstadoImpresora(responde=True, en_linea=False, tapa_abierta=True)
    w, config = asistente(usb=usb, prueba=lambda codigo: tp.ResultadoPrueba(
        exito_tecnico=False, codigo=codigo, problema=tp.TAPA_ABIERTA, estado_antes=tapa))
    w.search()
    w.choose_found("usb:04b8:0e15:X4TK001234")
    return w, config


def caso_cola_trabada():
    colas = ResultadoListado(colas=[clasificar(dict(nombre="Cocina TCP", puerto="IP_192.168.1.70",
                                                    driver="Generic / Text Only",
                                                    atributos=0x40))])
    w, config = asistente(colas=colas, prueba=lambda codigo: tp.ResultadoPrueba(
        exito_tecnico=False, codigo=codigo, problema=tp.EN_COLA, trabajo=TrabajoFalso(),
        trabajo_borrado=True))
    w.search()
    w.choose_found("windows:cocina tcp")
    return w, config


def caso_nada_encontrado():
    w, config = asistente(red=nd.NetworkSearchResult(
        adapters=[PC, VPN], swept=255, seconds=1.5,
        notes=["Se ignoró la conexión VPN \"VPN Oficina\"."]))
    w.search()
    return w, config


def caso_otra_subred():
    w, config = asistente(probe=lambda h, p: TCP_SIN_RESPUESTA)
    w.choose_address()
    w.submit_address("192.168.123.100")
    return w, config


CASOS = {
    "exito_red": caso_exito_red,
    "usb_tapa_abierta": caso_usb_tapa_abierta,
    "cola_trabada": caso_cola_trabada,
    "nada_encontrado": caso_nada_encontrado,
    "otra_subred": caso_otra_subred,
}


@pytest.mark.parametrize("caso", sorted(CASOS))
def test_snapshot_aprobado(caso):
    texto = reporte(*CASOS[caso]())
    ruta = os.path.join(SNAPSHOTS, f"diagnostico_{caso}.txt")
    if os.environ.get("FISCALBERRY_UPDATE_SNAPSHOTS") == "1":
        os.makedirs(SNAPSHOTS, exist_ok=True)
        with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto + "\n")
    with open(ruta, encoding="utf-8") as fh:
        assert texto + "\n" == fh.read()


@pytest.mark.parametrize("caso", sorted(CASOS))
def test_ningun_secreto_ni_su_clave_aparece(caso):
    texto = reporte(*CASOS[caso]())
    for valor in VALORES_SECRETOS:
        assert valor not in texto, valor
    for clave in CLAVES_SECRETAS:
        assert clave not in texto.lower(), clave


def test_el_reporte_dice_el_paso_exacto_donde_fallo():
    texto = reporte(*caso_usb_tapa_abierta())
    assert "Paso actual: problema" in texto
    assert "Resultado técnico: falló (tapa_abierta)" in texto
    assert "tapa abierta=sí" in texto
    assert "Identidad: usb:04b8:0e15:…1234" in texto
    recorrido = texto.split("== Recorrido")[1]
    assert (recorrido.index("eligio") < recorrido.index("· prueba")
            < recorrido.index("problema=tapa_abierta"))


def test_la_cola_trabada_dice_que_el_trabajo_se_borro():
    texto = reporte(*caso_cola_trabada())
    assert "Trabajo de prueba borrado de la cola: sí" in texto
    # Por una cola de Windows no se lee el estado: no se inventa uno.
    assert "DLE EOT" not in texto.split("== Última prueba")[1].split("==")[0]


def test_lo_identificable_se_reduce():
    texto = reporte(*caso_exito_red())
    assert "00:26:AB:xx:xx:xx" in texto and "12:34:56" not in texto
    assert "A4:BB:6D:xx:xx:xx" in texto
    usb = reporte(*caso_usb_tapa_abierta())
    assert "X4TK001234" not in usb and "Conexión: USB (…1234)" in usb
    assert "Equipo: id …9c0d" in texto


def test_la_ultima_prueba_queda_aunque_ya_se_haya_guardado():
    texto = reporte(*caso_exito_red())
    assert "Resultado técnico: bien" in texto and "Papel confirmado: sí" in texto


def test_ip_publica_y_carpeta_del_usuario():
    assert sr.redact_ip("200.45.1.9") == "IP pública (oculta)"
    assert sr.redact_ip("192.168.1.9") == "192.168.1.9"
    assert sr.redact_identity("network:8.8.8.8:9100") == "network:IP pública (oculta):9100"
    home = os.path.expanduser("~")
    assert sr.scrub(f"log en {home}/logs y C:\\Users\\Juan\\AppData") == \
        "log en ~/logs y C:\\Users\\<usuario>\\AppData"


def test_una_ip_publica_escrita_a_mano_no_queda_en_el_recorrido():
    w, config = asistente(probe=lambda h, p: TCP_SIN_RESPUESTA)
    w.choose_address()
    w.submit_address("200.45.17.9")
    texto = reporte(w, config)
    assert "200.45.17.9" not in texto and "IP pública (oculta)" in texto


def test_jwt_y_tokens_sueltos_se_ocultan():
    texto = sr.scrub("jwt: eyJabcdefghij.eyJklmnopqrst.firmafirmafirma y token=abc123 Bearer xyz")
    assert "eyJ" not in texto and "abc123" not in texto and "xyz" not in texto


def test_sin_asistente_igual_hay_reporte():
    texto = sr.build_report(None, dict(SECRETOS), now=datetime(2026, 9, 25), version="3.9.9",
                            installation="source", system="Linux",
                            service="sin datos", log_lines=[], adapters=[])
    assert "El asistente no se abrió en esta sesión." in texto
    assert "- Caja: driver=Win32Raw" in texto
    for valor in VALORES_SECRETOS:
        assert valor not in texto


def test_si_algo_revienta_el_reporte_igual_sale(monkeypatch):
    monkeypatch.setattr(sr, "collect_lines", lambda *a, **k: 1 / 0)
    texto = sr.build_report(None, dict(SECRETOS))
    assert "No se pudo armar el diagnóstico completo" in texto


def test_se_guarda_junto_al_registro(tmp_path):
    ruta = sr.save_report("hola", carpeta=str(tmp_path))
    assert open(ruta, encoding="utf-8").read() == "hola"


def test_solo_entran_errores_del_asistente(tmp_path, monkeypatch):
    from fiscalberry.common import fiscalberry_logger

    log = tmp_path / "fiscalberry.log"
    log.write_text("\n".join([
        "2026-09-25 14:00:00 [app:1] INFO PrinterWizard: paso inicio",
        "2026-09-25 14:00:01 [app:1] ERROR RabbitMQ: ticket {\"total\": 1500}",
        "2026-09-25 14:00:02 [app:1] WARNING UsbPrint: ocupada, reintento",
    ]), encoding="utf-8")
    monkeypatch.setattr(fiscalberry_logger, "readLogTail",
                        lambda max_bytes=0, path=None: log.read_text(encoding="utf-8"))
    assert sr._lineas_de_log() == [
        "2026-09-25 14:00:02 [app:1] WARNING UsbPrint: ocupada, reintento"]


# ---------------------------------------------------------------------------
# La pantalla: "Copiar diagnóstico" y "Ver registro"
# ---------------------------------------------------------------------------

@pytest.fixture
def pantalla(monkeypatch):
    pytest.importorskip("kivy")
    from kivy.app import App
    from kivy.lang import Builder
    from kivy.properties import NumericProperty, StringProperty
    from kivy.uix.screenmanager import Screen, ScreenManager

    class AppMinima(App):
        inset_top = NumericProperty(0)
        inset_bottom = NumericProperty(0)
        siteName = StringProperty("Pizzeria")
        siteAlias = StringProperty("")

        def leave_printer_setup(self, motivo):
            pass

    app = AppMinima()
    monkeypatch.setattr(App, "_running_app", app)
    from fiscalberry.ui import printer_setup_screen as pss

    kv = os.path.join(os.path.dirname(pss.__file__), "kv", "printer_setup.kv")
    Builder.load_file(kv)
    try:
        sm = ScreenManager()
        logs = Screen(name="logs")
        logs.volver_a = "main"
        sm.add_widget(logs)
        s = pss.PrinterSetupScreen(name="printer_setup")
        sm.add_widget(s)
        sm.current = "printer_setup"
        yield pss, s, sm
    finally:
        Builder.unload_file(kv)


def test_copiar_diagnostico_y_ver_registro(pantalla, monkeypatch, tmp_path):
    pss, s, sm = pantalla
    w, config = caso_usb_tapa_abierta()
    w.on_change = s._sync
    s.wizard = w
    s._sync()
    assert s.ids.pasos.current == "problema"

    copiado = {}
    monkeypatch.setattr(pss, "copiar_al_portapapeles", lambda texto: copiado.setdefault("t", texto))
    monkeypatch.setattr(pss, "armar_diagnostico", lambda wizard: reporte(wizard, config))
    monkeypatch.setattr(sr, "save_report", lambda texto: str(tmp_path / "d.txt"))
    s.copy_diagnosis()
    assert "Resultado técnico: falló (tapa_abierta)" in copiado["t"]
    assert s.diagnosis_status.startswith("Copiado")

    s.view_log()
    assert sm.current == "logs"
    assert sm.get_screen("logs").volver_a == "printer_setup"


def test_si_no_se_puede_copiar_queda_el_archivo(pantalla, monkeypatch, tmp_path):
    pss, s, _ = pantalla
    w, config = caso_usb_tapa_abierta()
    s.wizard = w

    def sin_portapapeles(texto):
        raise RuntimeError("sin portapapeles")

    monkeypatch.setattr(pss, "copiar_al_portapapeles", sin_portapapeles)
    monkeypatch.setattr(pss, "armar_diagnostico", lambda wizard: reporte(wizard, config))
    monkeypatch.setattr(sr, "save_report", lambda texto: str(tmp_path / "d.txt"))
    s.copy_diagnosis()
    assert "Quedó guardado" in s.diagnosis_status
