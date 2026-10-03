# coding=utf-8
"""
"Buscar impresoras" (#184): red, USB/COM y colas de Windows en un solo
listado, y el recorrido de los escenarios 1 a 4 (más la detección de otra
subred) sin Kivy.

Las fuentes son falsas pero devuelven los mismos objetos que las reales
(NetworkSearchResult, UsbSearchResult, ResultadoListado).
"""

import threading
import time

import pytest

from fiscalberry.common import network_discovery as nd
from fiscalberry.common import printer_search as ps
from fiscalberry.common import printer_wizard as pw
from fiscalberry.common import ticket_prueba as tp
from fiscalberry.common.printer_setup import (
    PrinterSetupService, TCP_OK, TCP_RECHAZADO, TCP_SIN_RESPUESTA)
from fiscalberry.common.usb_discovery import (
    INCOMPATIBLE_NO_DRIVER, IncompatibleUsb, SerialPort, UsbPrintDevice, UsbSearchResult)
from fiscalberry.common.windows_queues import (
    ERROR_NO_WINDOWS, ERROR_TIMEOUT, ColaWindows, ResultadoListado, clasificar)

GUID = "{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"
RUTA_USB = r"\\?\usb#vid_04b8&pid_0e15#X4TK001#" + GUID
RUTA_USB_2 = r"\\?\usb#vid_0fe6&pid_811e#6&2c5b3a7&0&2#" + GUID
PC = nd.NetworkAdapter(name="Ethernet", address="192.168.1.27", prefix=24,
                       gateways=("192.168.1.1",))


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


def cola(nombre, puerto, driver="Generic / Text Only", atributos=0x40, **kw):
    return clasificar(dict(nombre=nombre, puerto=puerto, driver=driver, atributos=atributos, **kw))


def colas(*lista, **kw):
    return ResultadoListado(colas=list(lista), **kw)


EPSON_USB = UsbPrintDevice(RUTA_USB, 0x04B8, 0x0E15, "X4TK001", "USB001",
                           ieee1284={"MFG": "EPSON", "MDL": "TM-T20II"})
GENERICA_USB = UsbPrintDevice(RUTA_USB_2, 0x0FE6, 0x811E, "", "USB002")
COM_CH340 = SerialPort("COM4", "USB-SERIAL CH340 (COM4)", "USB VID:PID=1A86:7523", 0x1A86, 0x7523)
COM_PLACA = SerialPort("COM1", "Puerto de comunicaciones (COM1)", "ACPI\\PNP0501", kind="placa")
COLA_USB001 = cola("EPSON TM-T20II Receipt", "USB001", "EPSON TM-T20II Receipt5")
COLA_IP = cola("Cocina", "IP_192.168.1.50")
COLA_PDF = cola("Microsoft Print to PDF", "PORTPROMPT:", "Microsoft Print To PDF")
COLA_OFFLINE = cola("POS-58", "USB003", "POS-58", atributos=0x40 | 0x400)

CLAVE_EPSON_USB = "usb:04b8:0e15:X4TK001"
CLAVE_COLA = "windows:epson tm-t20ii receipt"


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
    assert {f.subtitle for f in visibles} == {"Conectada a la red", "Conectada por USB",
                                              "Instalada en Windows", "Conectada por cable USB"}
    # Nada técnico en la frase: eso va en "Ver detalles".
    for f in visibles:
        for palabra in ("IP", "9100", "driver", "COM4", "USB00"):
            assert palabra not in f.subtitle
    assert "Dirección IP: 192.168.1.60" in visibles[0].details
    assert "Puerto: 9100" in visibles[0].details


def test_la_cola_tapa_a_la_misma_impresora_usb_y_la_red_tapa_a_su_cola():
    encontradas, _ = ps.merge(red(de_red("192.168.1.50")), usb([EPSON_USB]),
                              colas(COLA_USB001, COLA_IP))
    por_clave = {f.key: f for f in encontradas}
    assert por_clave[CLAVE_EPSON_USB].hidden
    assert "EPSON TM-T20II Receipt" in por_clave[CLAVE_EPSON_USB].hidden_reason
    assert por_clave["windows:cocina"].hidden
    assert "192.168.1.50" in por_clave["windows:cocina"].hidden_reason
    assert not por_clave[CLAVE_COLA].hidden
    assert not por_clave["network:192.168.1.50:9100"].hidden


def test_la_cola_tapa_al_mismo_com():
    encontradas, _ = ps.merge(None, usb(serial=[COM_CH340]), colas(cola("Barra", "COM4:")))
    com = next(f for f in encontradas if f.source == ps.SOURCE_SERIAL)
    assert com.hidden and "Barra" in com.hidden_reason


def test_virtuales_offline_y_placa_quedan_para_mostrar_todas():
    r = ps.SearchResult()
    r.found, _ = ps.merge(None, usb(serial=[COM_PLACA]), colas(COLA_PDF, COLA_OFFLINE))
    assert r.visible() == []
    assert {f.title for f in r.visible(show_all=True)} == {"Microsoft Print to PDF", "POS-58",
                                                          "Puerto COM1"}
    assert r.hidden_count == 3


def test_una_cola_repetida_aparece_una_vez():
    encontradas, _ = ps.merge(None, None, colas(COLA_USB001, cola("epson tm-t20ii receipt",
                                                                  "USB001")))
    assert len(encontradas) == 1


def test_la_predeterminada_de_windows_va_primero():
    otra = cola("Barra", "USB002")
    predeterminada = cola("Caja", "USB003", predeterminada=True)
    encontradas, _ = ps.merge(None, None, colas(otra, predeterminada))
    assert [f.title for f in encontradas] == ["Caja", "Barra"]


def test_ya_configuradas_se_marcan_y_no_se_pueden_elegir():
    servicio = PrinterSetupService(ConfigFalso({"Caja": {"driver": "Network",
                                                         "host": "192.168.1.60", "port": "9100"}}))
    encontradas, _ = ps.merge(red(de_red("192.168.1.60"), de_red("192.168.1.61")), None, None,
                              servicio)
    assert [(f.key, f.configured_as) for f in encontradas] == [
        ("network:192.168.1.61:9100", ""), ("network:192.168.1.60:9100", "Caja")]
    assert not encontradas[1].selectable


def test_incompatibles_se_explican_y_no_tienen_candidato():
    encontradas, _ = ps.merge(None, usb(incompatibles=[
        IncompatibleUsb(0x04B8, 0x0202, INCOMPATIBLE_NO_DRIVER)]), None)
    f = encontradas[0]
    assert f.candidate is None and not f.selectable
    assert "driver del fabricante" in f.note


def test_avisos_de_cada_fuente():
    _, avisos = ps.merge(red(notas=["Se ignoró la conexión VPN \"Oficina\"."]),
                         UsbSearchResult(errors=["No se pudieron revisar los puertos COM."]),
                         colas(error=ERROR_TIMEOUT))
    assert avisos[:2] == ["Se ignoró la conexión VPN \"Oficina\".",
                          "No se pudieron revisar los puertos COM."]
    assert "tardó demasiado" in avisos[2]


def test_fuera_de_windows_no_se_avisa_que_no_hay_colas():
    _, avisos = ps.merge(red(), None, colas(error=ERROR_NO_WINDOWS))
    assert avisos == []


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
            liberar_colas.set()  # red y USB llegaron sin esperar a las colas

    final = busqueda.run(on_partial=parcial)
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
    """print_test de mentira: devuelve los resultados que se le indiquen."""

    def __init__(self, *resultados):
        self.resultados = list(resultados)
        self.pruebas = []

    def __call__(self, candidato, alias, comercio, codigo):
        self.pruebas.append((candidato, alias, comercio, codigo))
        r = self.resultados.pop(0) if len(self.resultados) > 1 else self.resultados[0]
        return r(codigo) if callable(r) else r


def ok(codigo="K7QX"):
    return tp.ResultadoPrueba(exito_tecnico=True, codigo=codigo)


class TrabajoFalso:
    def __init__(self):
        self.cancelado = False

    def cancelar(self):
        self.cancelado = True
        return True


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
                         list_adapters=lambda: list(adaptadores), new_code=lambda: "K7QX")
    return w, config, salidas


def recorrer(w, clave, nombre):
    w.search()
    assert w.step == pw.STEP_RESULTS and not w.searching
    w.choose_found(clave)
    assert w.step == pw.STEP_CONFIRM, w.message
    w.confirm_paper(True)
    w.save(nombre)
    assert w.step == pw.STEP_SAVED


@pytest.mark.parametrize("escenario,fuentes,clave,driver", [
    (1, dict(network=red(de_red("192.168.1.60", "TM-T88V"))), "network:192.168.1.60:9100",
     "Network"),
    (2, dict(usb_=usb([EPSON_USB])), CLAVE_EPSON_USB, "UsbPrint"),
    (3, dict(usb_=usb(serial=[COM_CH340])), "serial:com4", "Serial"),
    (4, dict(queues=colas(COLA_USB001)), CLAVE_COLA, "Win32Raw"),
])
def test_escenarios_1_a_4_de_punta_a_punta(escenario, fuentes, clave, driver):
    impresora = Impresora(ok)
    w, config, salidas = asistente(buscador(**fuentes), impresora)
    recorrer(w, clave, "Cocina")
    candidato, alias, comercio, codigo = impresora.pruebas[0]
    assert candidato.driver_config["driver"] == driver
    assert (alias, comercio, codigo) == ("Impresora", "Pizzeria", "K7QX")
    assert config.writes == ["Cocina"]
    assert config.data["Cocina"]["driver"] == driver
    assert config.data["Cocina"]["_setup_id"] == clave
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
    assert w.suggested_alias == "Impresora"
    w.save("Barra")
    assert w.saved == ["Cocina", "Barra"]


def test_elegir_una_ya_configurada_lo_explica_sin_probar():
    config = ConfigFalso({"Caja": {"driver": "Win32Raw",
                                   "printer_name": "EPSON TM-T20II Receipt"}})
    impresora = Impresora(ok)
    w, _, _ = asistente(buscador(queues=colas(COLA_USB001)), impresora, config=config)
    w.search()
    w.choose_found(CLAVE_COLA)
    assert w.step == pw.STEP_PROBLEM and "Caja" in w.message
    assert impresora.pruebas == []


def test_una_incompatible_se_explica_y_no_se_prueba():
    impresora = Impresora(ok)
    w, _, _ = asistente(buscador(usb_=usb(incompatibles=[
        IncompatibleUsb(0x04B8, 0x0202, INCOMPATIBLE_NO_DRIVER)])), impresora)
    w.search()
    w.choose_found("incompatible:04B8:0202")
    assert w.step == pw.STEP_PROBLEM and "driver del fabricante" in w.message
    assert impresora.pruebas == []


def test_si_no_hay_nada_se_explica():
    w, _, _ = asistente(buscador())
    w.search()
    assert w.step == pw.STEP_RESULTS and w.found == []
    assert w.message == pw.NOTHING_FOUND


def test_la_prueba_trabada_en_una_cola_vuelve_a_la_lista_sin_guardar():
    trabada = tp.ResultadoPrueba(exito_tecnico=False, codigo="K7QX", problema=tp.EN_COLA)
    w, config, _ = asistente(buscador(queues=colas(COLA_USB001)), Impresora(trabada))
    w.search()
    w.choose_found(CLAVE_COLA)
    assert w.step == pw.STEP_PROBLEM and w.message == tp.ACCIONES[tp.EN_COLA]
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


# ---- otra subred: solo se explica ----------------------------------------------

@pytest.mark.parametrize("direccion,respuesta,texto", [
    ("192.168.123.100", TCP_SIN_RESPUESTA, "Xprinter"),
    ("192.168.192.168", TCP_SIN_RESPUESTA, "Epson"),
    ("192.168.123.68", TCP_SIN_RESPUESTA, "192.168.1.x"),
    ("192.168.1.1", TCP_RECHAZADO, "router"),
    ("192.168.1.80", TCP_SIN_RESPUESTA, "Nadie respondió"),
    ("192.168.1.27", TCP_OK, "esta computadora"),
])
def test_direccion_escrita_que_no_se_puede_usar(direccion, respuesta, texto):
    impresora = Impresora(ok)
    w, _, _ = asistente(buscador(), impresora, probe=lambda h, p: respuesta)
    w.choose_address()
    w.submit_address(direccion)
    assert w.step == pw.STEP_ADDRESS
    assert texto in w.message
    assert impresora.pruebas == []


def test_direccion_de_otra_subred_pero_con_ruta_se_prueba():
    w, _, _ = asistente(buscador(), probe=lambda h, p: TCP_OK)
    w.choose_address()
    w.submit_address("192.168.123.100")
    assert w.step == pw.STEP_CONFIRM
    assert w.diagnosis.kind == nd.KIND_ROUTED


def test_la_direccion_usa_los_adaptadores_de_la_busqueda():
    usados = []
    w, _, _ = asistente(buscador(network=red()), probe=lambda h, p: TCP_SIN_RESPUESTA,
                        adaptadores=())
    w._list_adapters = lambda: usados.append(1) or []
    w.search()
    w.choose_address()
    w.submit_address("192.168.123.68")
    assert usados == []  # no volvió a leerlos
    assert "otra red" in w.message


# ---- asincronía: nada de lo lento en el hilo de la interfaz --------------------

class RunnerDiferido:
    def __init__(self):
        self.pendientes = []

    def __call__(self, fn, on_done):
        self.pendientes.append((fn, on_done))

    def terminar(self):
        while self.pendientes:
            fn, on_done = self.pendientes.pop(0)
            on_done(pw.capturar(fn))


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

    def buscar(cancel=None, on_partial=None):
        parcial = ps.SearchResult(pending={ps.SOURCE_WINDOWS})
        parcial.found, _ = ps.merge(red(de_red("192.168.1.60")))
        on_partial(parcial)
        return parcial

    w, _, _ = asistente(buscar)
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
    assert prueba["conexion"] == "network"


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
    s.wizard = pw.PrinterWizard(
        servicio, search=ps.PrinterSearch(servicio,
                                          network=fuente(red(de_red("192.168.1.60", "TM-T88V"))),
                                          usb=fuente(usb([EPSON_USB])),
                                          queues=fuente(colas(COLA_USB001, COLA_PDF), 0.3)).run,
        runner=pss.kivy_runner, post=pss.kivy_post, print_test=Impresora(ok),
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
