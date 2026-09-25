# coding=utf-8
"""
"Buscar impresoras" (#184): red, USB/COM y colas de Windows en un solo
listado, y el recorrido de los escenarios 1 a 4 (más la detección del 5).

Las fuentes son falsas pero devuelven los mismos objetos que las reales
(NetworkSearchResult, UsbSearchResult, QueueListResult). Al final, la
pantalla Kivy real con trabajos en hilos y Clock: ningún trabajo corre en el
hilo de Kivy y los resultados llegan con Clock.
"""

import threading
import time

import pytest

from fiscalberry.common import network_discovery as nd
from fiscalberry.common import printer_search as ps
from fiscalberry.common import printer_wizard as pw
from fiscalberry.common.printer_guides import (
    GUIDE_NOT_FOUND, GUIDE_OTHER_NETWORK, GUIDE_OTHER_NETWORK_KNOWN, GUIDE_USB_DRIVER, guide_url)
from fiscalberry.common.printer_setup import PrinterSetupService, TCP_NO_RESPONSE, TCP_OK, TCP_REFUSED
from fiscalberry.common.printer_test import PROBLEM_JOB_STUCK, PrintTestResult
from fiscalberry.common.usb_discovery import (
    INCOMPATIBLE_NO_DRIVER, IncompatibleUsb, SerialPort, UsbPrintDevice, UsbSearchResult)
from fiscalberry.common.windows_queues import QueueListResult, WindowsQueue

GUID = "{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"
RUTA_USB = r"\\?\usb#vid_04b8&pid_0e15#X4TK001#" + GUID
RUTA_USB_2 = r"\\?\usb#vid_0fe6&pid_811e#6&2c5b3a7&0&2#" + GUID
PC = nd.NetworkAdapter(name="Ethernet", address="192.168.1.27", prefix=24, gateways=("192.168.1.1",))


class ConfigFalso:
    def __init__(self, data=None):
        self.data = {"SERVIDOR": {"uuid": "x"}}
        self.data.update(data or {})
        self.writes = []

    def get_actual_config(self):
        return {s: dict(v) for s, v in self.data.items()}

    def set(self, section, values):
        self.writes.append(section)
        self.data[section] = dict(values)
        return True


def red(*impresoras, notas=()):
    return nd.NetworkSearchResult(adapters=[PC], printers=list(impresoras), notes=list(notas))


def de_red(host, modelo="", puerto=9100, **kw):
    return nd.NetworkPrinter(host=host, port=puerto, adapter=PC, model=modelo, **kw)


def usb(usbprint=(), serial=(), incompatibles=()):
    return UsbSearchResult(usbprint=list(usbprint), serial=list(serial),
                           incompatible=list(incompatibles))


def colas(*lista, **kw):
    return QueueListResult(queues=list(lista), **kw)


EPSON_USB = UsbPrintDevice(RUTA_USB, 0x04B8, 0x0E15, "X4TK001", "USB001",
                           ieee1284={"MFG": "EPSON", "MDL": "TM-T20II"})
GENERICA_USB = UsbPrintDevice(RUTA_USB_2, 0x0FE6, 0x811E, "", "USB002")
COM_CH340 = SerialPort("COM4", "USB-SERIAL CH340 (COM4)", "USB VID:PID=1A86:7523", 0x1A86, 0x7523)
COM_PLACA = SerialPort("COM1", "Puerto de comunicaciones (COM1)", "ACPI\\PNP0501", kind="placa")
COLA_USB001 = WindowsQueue("EPSON TM-T20II Receipt", "USB001", "EPSON TM-T20II Receipt5",
                           attributes=0x40)
COLA_IP = WindowsQueue("Cocina", "IP_192.168.1.50", "Generic / Text Only", attributes=0x40)
COLA_PDF = WindowsQueue("Microsoft Print to PDF", "PORTPROMPT:", "Microsoft Print To PDF",
                        attributes=0x40)
COLA_OFFLINE = WindowsQueue("POS-58", "USB003", "POS-58", attributes=0x40 | 0x400)


# ---------------------------------------------------------------------------
# Un solo listado
# ---------------------------------------------------------------------------

def test_las_tres_fuentes_en_una_lista_sin_jerga():
    encontradas, _ = ps.merge(red(de_red("192.168.1.60", "TM-T88V")),
                              usb([GENERICA_USB], [COM_CH340]),
                              colas(COLA_USB001))
    visibles = [f for f in encontradas if not f.hidden]
    assert [f.title for f in visibles] == ["TM-T88V", "Impresora USB",
                                           "EPSON TM-T20II Receipt", "Impresora USB (COM4)"]
    subtitulos = {f.subtitle for f in visibles}
    assert subtitulos == {"Conectada a la red", "Conectada por USB", "Instalada en Windows",
                          "Conectada por cable USB"}
    # Nada técnico en el título ni en la frase: eso va en Detalles.
    for f in visibles:
        for palabra in ("IP", "9100", "driver", "COM4", "USB00"):
            assert palabra not in f.subtitle
    red_item = visibles[0]
    assert "Dirección IP: 192.168.1.60" in red_item.details and "Puerto: 9100" in red_item.details


def test_la_cola_tapa_a_la_misma_impresora_usb_y_la_red_tapa_a_su_cola():
    encontradas, _ = ps.merge(red(de_red("192.168.1.50")), usb([EPSON_USB]),
                              colas(COLA_USB001, COLA_IP))
    por_clave = {f.key: f for f in encontradas}
    usbprint = por_clave["usbprint:04b8:0e15:X4TK001"]
    assert usbprint.hidden and "EPSON TM-T20II Receipt" in usbprint.hidden_reason
    cola_ip = por_clave["windows:cocina"]
    assert cola_ip.hidden and "192.168.1.50" in cola_ip.hidden_reason
    assert not por_clave["windows:epson tm-t20ii receipt"].hidden
    assert not por_clave["network:192.168.1.50:9100"].hidden


def test_la_cola_tapa_al_mismo_com():
    cola_com = WindowsQueue("Barra", "COM4:", "Generic / Text Only", attributes=0x40)
    encontradas, _ = ps.merge(None, usb(serial=[COM_CH340]), colas(cola_com))
    com = next(f for f in encontradas if f.source == ps.SOURCE_SERIAL)
    assert com.hidden and "Barra" in com.hidden_reason


def test_virtuales_offline_y_placa_quedan_para_mostrar_todas():
    r = ps.SearchResult()
    r.found, _ = ps.merge(None, usb(serial=[COM_PLACA]), colas(COLA_PDF, COLA_OFFLINE))
    assert r.visible() == []
    assert {f.title for f in r.visible(show_all=True)} == {"Microsoft Print to PDF", "POS-58",
                                                          "Puerto COM1"}
    assert r.hidden_count == 3


def test_ya_configuradas_se_marcan_y_no_se_pueden_elegir():
    servicio = PrinterSetupService(ConfigFalso({"Caja": {"driver": "Network", "host": "192.168.1.60",
                                                         "port": "9100"}}))
    encontradas, _ = ps.merge(red(de_red("192.168.1.60"), de_red("192.168.1.61")), None, None,
                              servicio)
    assert [(f.key, f.configured_as) for f in encontradas] == [
        ("network:192.168.1.61:9100", ""), ("network:192.168.1.60:9100", "Caja")]
    assert not encontradas[1].selectable


def test_incompatibles_con_guia_y_sin_candidato():
    encontradas, _ = ps.merge(None, usb(incompatibles=[IncompatibleUsb(0x04B8, 0x0202,
                                                                       INCOMPATIBLE_NO_DRIVER)]),
                              None)
    f = encontradas[0]
    assert f.candidate is None and f.guide == GUIDE_USB_DRIVER
    assert "driver del fabricante" in f.note
    assert guide_url(f.guide).startswith("https://doc.paxapos.com/")


def test_avisos_de_cada_fuente():
    _, avisos = ps.merge(red(notas=["Se ignoró la conexión VPN \"Oficina\"."]),
                         UsbSearchResult(errors=["No se pudieron revisar los puertos COM."]),
                         colas(timed_out=True, local_only=True))
    assert avisos == ["Se ignoró la conexión VPN \"Oficina\".",
                      "No se pudieron revisar los puertos COM.",
                      "Una impresora compartida de otra computadora no respondió: "
                      "se muestran solo las de esta computadora."]


# ---------------------------------------------------------------------------
# En paralelo, con resultados parciales
# ---------------------------------------------------------------------------

def test_las_fuentes_corren_en_paralelo_y_avisan_de_a_una():
    liberar_colas = threading.Event()
    parciales = []

    def colas_lentas(cancel=None):
        liberar_colas.wait(5)
        return colas(COLA_USB001)

    busqueda = ps.PrinterSearch(
        network=lambda cancel=None: red(de_red("192.168.1.60")),
        usb=lambda cancel=None: usb([GENERICA_USB]),
        queues=colas_lentas)

    def parcial(r):
        parciales.append((set(r.pending), len(r.found)))
        if len(parciales) == 2:
            liberar_colas.set()  # red y USB ya llegaron sin esperar a las colas

    final = busqueda.run(on_partial=parcial)
    # Red y USB llegan primero (en cualquier orden); las colas, después.
    assert len(parciales[0][0]) == 2 and ps.SOURCE_WINDOWS in parciales[0][0]
    assert parciales[1][0] == {ps.SOURCE_WINDOWS}
    assert parciales[2] == (set(), 3)
    assert final.done and len(final.found) == 3


def test_una_fuente_que_revienta_no_tapa_a_las_demas():
    def rota(cancel=None):
        raise RuntimeError("SetupDi explotó")

    final = ps.PrinterSearch(network=lambda cancel=None: red(de_red("192.168.1.60")),
                             usb=rota, queues=lambda cancel=None: colas()).run()
    assert [f.key for f in final.found] == ["network:192.168.1.60:9100"]
    assert "No se pudieron revisar las impresoras USB." in final.notes


def test_cancelar_corta_la_espera():
    cancelar = threading.Event()

    def colgada(cancel=None):
        cancel.wait(10)
        return None

    threading.Timer(0.2, cancelar.set).start()
    inicio = time.monotonic()
    final = ps.PrinterSearch(network=colgada, usb=colgada, queues=colgada).run(cancel=cancelar)
    assert final.cancelled and time.monotonic() - inicio < 2


# ---------------------------------------------------------------------------
# El recorrido (sin Kivy)
# ---------------------------------------------------------------------------

class Impresora:
    def __init__(self, *resultados):
        self.resultados = list(resultados)
        self.pruebas = []

    def __call__(self, candidate, info):
        self.pruebas.append(candidate)
        r = self.resultados.pop(0) if len(self.resultados) > 1 else self.resultados[0]
        return r() if callable(r) else r


def ok():
    return PrintTestResult(technical_success=True)


def buscador(network=None, usb_=None, queues=None):
    def buscar(cancel=None, on_partial=None):
        return ps.PrinterSearch(service=buscar.servicio,
                                network=lambda cancel=None: network or red(),
                                usb=lambda cancel=None: usb_ or usb(),
                                queues=lambda cancel=None: queues or colas()
                                ).run(cancel=cancel, on_partial=on_partial)
    return buscar


def asistente(buscar, impresora=None, config=None, probe=lambda h, p: TCP_OK, adaptadores=(PC,)):
    config = config or ConfigFalso()
    servicio = PrinterSetupService(config)
    buscar.servicio = servicio
    salidas = []
    w = pw.PrinterWizard(servicio, commerce="Pizzeria", search=buscar, probe=probe,
                         print_test=impresora or Impresora(ok), on_exit=salidas.append,
                         list_adapters=lambda: list(adaptadores))
    return w, config, salidas


def recorrer(w, clave, alias):
    w.search()
    assert w.step == pw.STEP_RESULTS and not w.searching
    w.choose_found(clave)
    assert w.step == pw.STEP_CONFIRM, w.message
    w.confirm_paper(True)
    w.save(alias)
    assert w.step == pw.STEP_SAVED


@pytest.mark.parametrize("escenario,fuentes,clave,transporte", [
    (1, dict(network=red(de_red("192.168.1.60", "TM-T88V"))), "network:192.168.1.60:9100", "Network"),
    (2, dict(usb_=usb([EPSON_USB])), "usbprint:04b8:0e15:X4TK001", "UsbPrint"),
    (3, dict(usb_=usb(serial=[COM_CH340])), "serial:COM4", "Serial"),
    (4, dict(queues=colas(COLA_USB001)), "windows:epson tm-t20ii receipt", "Win32Raw"),
])
def test_escenarios_1_a_4_de_punta_a_punta(escenario, fuentes, clave, transporte):
    impresora = Impresora(ok)
    w, config, salidas = asistente(buscador(**fuentes), impresora)
    recorrer(w, clave, "Cocina")
    assert impresora.pruebas[0].transport == transporte
    assert config.writes == ["Cocina"]
    assert config.data["Cocina"]["driver"] == transporte
    w.finish()
    assert salidas == [pw.EXIT_FINISHED]


def test_agregar_otra_vuelve_a_la_lista_con_la_guardada_marcada():
    w, config, _ = asistente(buscador(network=red(de_red("192.168.1.60"), de_red("192.168.1.61"))))
    recorrer(w, "network:192.168.1.60:9100", "Cocina")
    w.add_another()
    assert w.step == pw.STEP_RESULTS
    marcas = {f.key: f.configured_as for f in w.found}
    assert marcas == {"network:192.168.1.60:9100": "Cocina", "network:192.168.1.61:9100": ""}
    w.choose_found("network:192.168.1.61:9100")
    w.confirm_paper(True)
    w.save("Barra")
    assert w.saved == ["Cocina", "Barra"]


def test_elegir_una_ya_configurada_lo_explica():
    config = ConfigFalso({"Caja": {"driver": "Win32Raw", "printer_name": "EPSON TM-T20II Receipt"}})
    impresora = Impresora(ok)
    w, _, _ = asistente(buscador(queues=colas(COLA_USB001)), impresora, config=config)
    w.search()
    w.choose_found("windows:epson tm-t20ii receipt")
    assert w.step == pw.STEP_PROBLEM and "Caja" in w.message
    assert impresora.pruebas == []


def test_una_incompatible_muestra_la_guia_y_no_prueba():
    w, _, _ = asistente(buscador(usb_=usb(incompatibles=[IncompatibleUsb(0x04B8, 0x0202,
                                                                          INCOMPATIBLE_NO_DRIVER)])))
    w.search()
    w.choose_found("incompatible:04B8:0202")
    assert w.step == pw.STEP_PROBLEM and w.guide == GUIDE_USB_DRIVER


def test_si_no_hay_nada_se_explica_con_la_guia():
    w, _, _ = asistente(buscador())
    w.search()
    assert w.step == pw.STEP_RESULTS and w.found == []
    assert w.message == pw.NOTHING_FOUND and w.guide == GUIDE_NOT_FOUND


def test_la_prueba_fallida_en_una_cola_vuelve_a_la_lista():
    fallida = PrintTestResult(technical_success=False, problem=PROBLEM_JOB_STUCK, job_cancelled=True)
    w, config, _ = asistente(buscador(queues=colas(COLA_USB001)), Impresora(fallida))
    w.search()
    w.choose_found("windows:epson tm-t20ii receipt")
    assert w.step == pw.STEP_PROBLEM and "canceló" in w.message
    w.back()
    assert w.step == pw.STEP_RESULTS and len(w.found) == 1
    assert config.writes == []


def test_mostrar_todas():
    w, _, _ = asistente(buscador(queues=colas(COLA_USB001, COLA_PDF)))
    w.search()
    assert [f.title for f in w.found] == ["EPSON TM-T20II Receipt"]
    assert w.hidden_count == 1
    w.toggle_show_all()
    assert len(w.found) == 2


# ---- escenario 5: solo detección, con la guía --------------------------------

@pytest.mark.parametrize("direccion,respuesta,guia,texto", [
    ("192.168.123.100", TCP_NO_RESPONSE, GUIDE_OTHER_NETWORK_KNOWN, "Xprinter"),
    ("192.168.192.168", TCP_NO_RESPONSE, GUIDE_OTHER_NETWORK_KNOWN, "Epson"),
    ("192.168.123.68", TCP_NO_RESPONSE, GUIDE_OTHER_NETWORK, "192.168.1.x"),
    ("192.168.1.1", TCP_REFUSED, "", "router"),
    ("192.168.1.80", TCP_NO_RESPONSE, "", "Nadie respondió"),
])
def test_direccion_escrita_que_no_se_puede_usar(direccion, respuesta, guia, texto):
    impresora = Impresora(ok)
    w, _, _ = asistente(buscador(), impresora, probe=lambda h, p: respuesta)
    w.choose_address()
    w.submit_address(direccion)
    assert w.step == pw.STEP_ADDRESS
    assert texto in w.message and w.guide == guia
    assert impresora.pruebas == []


def test_direccion_de_otra_subred_pero_con_ruta_se_prueba():
    impresora = Impresora(ok)
    w, _, _ = asistente(buscador(), impresora, probe=lambda h, p: TCP_OK)
    w.choose_address()
    w.submit_address("192.168.123.100")
    assert w.step == pw.STEP_CONFIRM
    assert w.diagnosis.kind == nd.KIND_ROUTED


def test_la_direccion_usa_los_adaptadores_de_la_busqueda():
    usados = []
    w, _, _ = asistente(buscador(network=red()), probe=lambda h, p: TCP_NO_RESPONSE,
                        adaptadores=())
    w._list_adapters = lambda: usados.append(1) or []
    w.search()
    w.choose_address()
    w.submit_address("192.168.123.68")
    assert usados == []  # no volvió a leerlos
    assert w.guide == GUIDE_OTHER_NETWORK


# ---- asincronía: nada de lo lento en el hilo de la interfaz --------------------

class RunnerDiferido:
    def __init__(self):
        self.pendientes = []

    def __call__(self, fn, on_done):
        self.pendientes.append((fn, on_done))

    def terminar(self):
        while self.pendientes:
            fn, on_done = self.pendientes.pop(0)
            on_done(pw._capturar(fn))


def test_salir_mientras_busca_cancela_y_descarta():
    runner = RunnerDiferido()
    vistos = {}

    def buscar(cancel=None, on_partial=None):
        vistos["cancel"] = cancel
        return ps.SearchResult(pending=set())

    w, _, salidas = asistente(buscar)
    w.runner = runner
    w.search()
    assert w.searching and w.step == pw.STEP_RESULTS
    w.skip()
    runner.terminar()
    assert vistos["cancel"].is_set()
    assert salidas == [pw.EXIT_SKIPPED]
    assert w.search_result is None


def test_dejar_de_buscar_muestra_lo_encontrado():
    runner = RunnerDiferido()

    def buscar(cancel=None, on_partial=None):
        parcial = ps.SearchResult(pending={ps.SOURCE_WINDOWS})
        parcial.found, _ = ps.merge(red(de_red("192.168.1.60")))
        on_partial(parcial)
        return parcial

    w, _, _ = asistente(buscar)
    w.runner = runner
    w.search()
    fn, on_done = runner.pendientes.pop(0)
    fn()  # llegan los parciales, pero la búsqueda "sigue"
    assert w.searching and len(w.found) == 1
    w.cancel_search()
    assert not w.searching and w.step == pw.STEP_RESULTS and len(w.found) == 1
    on_done(ps.SearchResult())  # el final tardío se descarta
    assert len(w.found) == 1


def test_elegir_mientras_busca_deja_de_buscar():
    runner = RunnerDiferido()
    impresora = Impresora(ok)

    def buscar(cancel=None, on_partial=None):
        parcial = ps.SearchResult(pending={ps.SOURCE_WINDOWS})
        parcial.found, _ = ps.merge(red(de_red("192.168.1.60")))
        on_partial(parcial)
        cancel.wait(0)  # no bloquea el test
        return parcial

    w, _, _ = asistente(buscar, impresora)
    w.runner = runner
    w.search()
    fn, _ = runner.pendientes.pop(0)
    fn()
    w.choose_found("network:192.168.1.60:9100")
    assert not w.searching and w.step == pw.STEP_TESTING
    runner.terminar()
    assert w.step == pw.STEP_CONFIRM


def test_el_diario_registra_cada_paso():
    w, _, _ = asistente(buscador(network=red(de_red("192.168.1.60"))))
    recorrer(w, "network:192.168.1.60:9100", "Cocina")
    eventos = [e["evento"] for e in w.journal]
    for esperado in ("busqueda", "eligio", "prueba", "resultado", "papel", "guardada"):
        assert esperado in eventos
    prueba = next(e for e in w.journal if e["evento"] == "prueba")
    assert prueba["transporte"] == "Network"


# ---------------------------------------------------------------------------
# La pantalla real (Kivy) con hilos y Clock
# ---------------------------------------------------------------------------

@pytest.fixture
def pantalla(monkeypatch):
    pytest.importorskip("kivy")
    import os

    from kivy.app import App
    from kivy.lang import Builder
    from kivy.properties import NumericProperty, StringProperty

    class AppMinima(App):
        inset_top = NumericProperty(0)
        inset_bottom = NumericProperty(0)
        siteName = StringProperty("Pizzeria")
        siteAlias = StringProperty("")

        def __init__(self, **kw):
            super().__init__(**kw)
            self.salidas = []

        def leave_printer_setup(self, motivo):
            self.salidas.append(motivo)

    app = AppMinima()
    monkeypatch.setattr(App, "_running_app", app)

    from fiscalberry.ui import printer_setup_screen as pss

    kv = os.path.join(os.path.dirname(pss.__file__), "kv", "printer_setup.kv")
    Builder.load_file(kv)
    try:
        yield pss, app
    finally:
        Builder.unload_file(kv)


def esperar(condicion, segundos=5):
    from kivy.clock import Clock
    limite = time.monotonic() + segundos
    while not condicion():
        if time.monotonic() > limite:
            raise AssertionError("la condición no se cumplió a tiempo")
        Clock.tick()
        time.sleep(0.01)


def test_la_pantalla_busca_en_hilos_y_muestra_la_lista(pantalla):
    pss, app = pantalla
    hilo_kivy = threading.current_thread()
    hilos_de_trabajo = []

    def fuente(valor, demora=0.0):
        def correr(cancel=None):
            hilos_de_trabajo.append(threading.current_thread())
            time.sleep(demora)
            return valor
        return correr

    s = pss.PrinterSetupScreen(name="printer_setup")
    config = ConfigFalso()
    servicio = PrinterSetupService(config)
    impresora = Impresora(ok)
    s.wizard = pw.PrinterWizard(
        servicio, search=ps.PrinterSearch(servicio,
                                          network=fuente(red(de_red("192.168.1.60", "TM-T88V"))),
                                          usb=fuente(usb([EPSON_USB])),
                                          queues=fuente(colas(COLA_USB001, COLA_PDF), 0.3)).run,
        runner=pss.kivy_runner, post=pss.kivy_post, print_test=impresora,
        on_change=s._sync, on_exit=s._exit, list_adapters=lambda: [PC])
    s.on_pre_enter()

    s.search()
    assert s.ids.pasos.current == "resultados" and s.searching
    esperar(lambda: not s.searching)
    assert hilo_kivy not in hilos_de_trabajo

    filas = list(reversed(s.ids.lista.children))
    assert [f.titulo for f in filas] == ["TM-T88V", "EPSON TM-T20II Receipt"]
    assert s.hidden_count == 2  # la usbprint tapada por su cola y el PDF
    assert filas[0].detalles and not filas[0].mostrar_detalles

    s.toggle_details()
    assert all(f.mostrar_detalles for f in s.ids.lista.children)
    s.toggle_show_all()
    assert len(s.ids.lista.children) == 4

    # Elegir con el teclado: Enter sobre la fila con foco.
    fila = next(f for f in s.ids.lista.children if f.titulo == "TM-T88V")
    fila.keyboard_on_key_down(None, (13, "enter"), "", [])
    esperar(lambda: s.step == "confirmar")
    assert s.test_code

    s.confirm_paper(True)
    assert s.ids.pasos.current == "nombre"
    s.save("Cocina")
    assert s.ids.pasos.current == "guardada" and config.writes == ["Cocina"]

    s.add_another()
    assert s.ids.pasos.current == "resultados"
    marcada = next(f for f in s.ids.lista.children if f.titulo == "TM-T88V")
    assert marcada.configurada == "Cocina"

    s.skip()
    assert app.salidas == [pw.EXIT_FINISHED]


def test_escape_vuelve_y_no_cierra_la_app(pantalla):
    pss, _ = pantalla
    s = pss.PrinterSetupScreen(name="printer_setup")
    s.wizard = pw.PrinterWizard(PrinterSetupService(ConfigFalso()), on_change=s._sync,
                                on_exit=s._exit, list_adapters=lambda: [])
    s.on_pre_enter()
    s.choose_address()
    assert s.ids.pasos.current == "direccion"
    assert s._on_keyboard(None, 27) is True
    assert s.ids.pasos.current == "inicio"
    # En el inicio Escape no hace nada, pero tampoco deja que Kivy cierre la app.
    assert s._on_keyboard(None, 27) is True
    assert s._on_keyboard(None, 13) is False


def test_el_foco_va_a_la_accion_principal(pantalla):
    from kivy.clock import Clock

    pss, _ = pantalla
    s = pss.PrinterSetupScreen(name="printer_setup")
    s.wizard = pw.PrinterWizard(PrinterSetupService(ConfigFalso()), on_change=s._sync,
                                on_exit=s._exit, list_adapters=lambda: [])
    s.on_pre_enter()
    s.wizard.start()
    s.choose_address()
    Clock.tick()
    assert s.ids.direccion.focus
    s.back()
    Clock.tick()
    assert s.ids.principal_inicio.focus

    # Enter sobre el botón con foco lo toca.
    tocado = []
    s.ids.principal_inicio.bind(on_press=lambda *_: tocado.append(1))
    s.ids.principal_inicio.keyboard_on_key_down(None, (13, "enter"), "", [])
    assert tocado == [1]
