# coding=utf-8
"""
Recorrido del asistente (#173): pasos, errores y salidas.

La lógica es PrinterWizard (sin Kivy); al final hay una prueba de humo de la
pantalla real para que el .kv no se rompa sin que nadie se entere.
"""

import pytest

from fiscalberry.common import printer_wizard as pw
from fiscalberry.common.printer_setup import (
    PrinterCandidate,
    PrinterSetupService,
    TCP_NO_RESPONSE,
    TCP_OK,
    TCP_REFUSED,
)
from fiscalberry.common.printer_test import PROBLEM_COVER_OPEN, PrintTestResult


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


class Impresora:
    """print_test de mentira: devuelve los resultados que se le indiquen."""

    def __init__(self, *resultados):
        self.resultados = list(resultados)
        self.pruebas = []

    def __call__(self, candidate, info):
        self.pruebas.append((candidate, info))
        resultado = self.resultados.pop(0) if len(self.resultados) > 1 else self.resultados[0]
        return resultado() if callable(resultado) else resultado


def ok():
    return PrintTestResult(technical_success=True)


def tapa_abierta():
    return PrintTestResult(technical_success=False, problem=PROBLEM_COVER_OPEN)


class Registro:
    def __init__(self):
        self.cambios = 0
        self.salidas = []


def asistente(config=None, probe=lambda host, port: TCP_OK, impresora=None, runner=pw.run_sync):
    reg = Registro()
    config = config or ConfigFalso()
    w = pw.PrinterWizard(
        PrinterSetupService(config),
        commerce="Pizzeria Don Pepe",
        runner=runner,
        probe=probe,
        print_test=impresora or Impresora(ok),
        on_change=lambda: setattr(reg, "cambios", reg.cambios + 1),
        on_exit=reg.salidas.append,
    )
    return w, reg, config


# ---------------------------------------------------------------------------
# El camino feliz
# ---------------------------------------------------------------------------

def test_de_la_direccion_a_la_impresora_guardada():
    impresora = Impresora(ok)
    w, reg, config = asistente(impresora=impresora)

    w.choose_address()
    assert w.step == pw.STEP_ADDRESS

    w.submit_address("192.168.1.80")
    assert w.step == pw.STEP_CONFIRM
    # El ticket lleva un código y el comercio para reconocerlo en papel.
    assert len(w.test_code) == 4
    candidato, info = impresora.pruebas[0]
    assert candidato.stable_id == "network:192.168.1.80:9100"
    assert info.commerce == "Pizzeria Don Pepe"
    assert config.writes == []  # nada guardado todavía

    w.confirm_paper(True)
    assert w.step == pw.STEP_NAME
    assert w.suggested_alias == "Impresora"

    w.save("Cocina")
    assert w.step == pw.STEP_SAVED
    assert w.saved == ["Cocina"]
    assert config.writes == ["Cocina"]
    assert config.data["Cocina"]["_setup_id"] == "network:192.168.1.80:9100"

    w.finish()
    assert reg.salidas == [pw.EXIT_FINISHED]
    assert reg.cambios > 0


def test_agregar_otra_en_el_mismo_recorrido():
    w, reg, config = asistente()
    for ip, nombre in (("192.168.1.80", "Cocina"), ("192.168.1.81", "Barra")):
        w.choose_address()
        w.submit_address(ip)
        w.confirm_paper(True)
        w.save(nombre)
        assert w.step == pw.STEP_SAVED
        w.add_another()
        assert w.step == pw.STEP_INTRO

    assert w.saved == ["Cocina", "Barra"]
    assert config.writes == ["Cocina", "Barra"]


# ---------------------------------------------------------------------------
# Errores con acción concreta, y nada guardado
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("direccion", ["", "192.168.1", "impresora", "999.1.1.1"])
def test_una_direccion_invalida_no_llega_a_la_red(direccion):
    def probe(host, port):
        pytest.fail("no debe diagnosticar datos inválidos")

    w, _, _ = asistente(probe=probe)
    w.choose_address()
    w.submit_address(direccion)

    assert w.step == pw.STEP_ADDRESS
    assert w.message


@pytest.mark.parametrize("respuesta", [TCP_REFUSED, TCP_NO_RESPONSE])
def test_si_no_responde_se_explica_y_no_se_imprime(respuesta):
    impresora = Impresora(ok)
    w, _, _ = asistente(probe=lambda h, p: respuesta, impresora=impresora)
    w.choose_address()
    w.submit_address("192.168.1.80")

    assert w.step == pw.STEP_ADDRESS
    assert w.message == pw.PROBE_MESSAGES[respuesta]
    assert impresora.pruebas == []


def test_una_prueba_fallida_muestra_la_accion_y_se_puede_reintentar():
    impresora = Impresora(tapa_abierta, ok)
    w, _, config = asistente(impresora=impresora)
    w.choose_address()
    w.submit_address("192.168.1.80")

    assert w.step == pw.STEP_PROBLEM
    assert "tapa" in w.message.lower()

    w.retry()
    assert w.step == pw.STEP_CONFIRM
    assert len(impresora.pruebas) == 2
    assert config.writes == []


def test_si_el_ticket_no_salio_no_se_guarda():
    w, _, config = asistente()
    w.choose_address()
    w.submit_address("192.168.1.80")
    w.confirm_paper(False)

    assert w.step == pw.STEP_PROBLEM
    assert w.message == pw.PAPER_NOT_PRINTED
    w.save("Cocina")  # aunque la interfaz lo intentara
    assert config.writes == []


def test_una_impresora_ya_configurada_no_se_vuelve_a_probar():
    impresora = Impresora(ok)
    config = ConfigFalso({"Caja": {"driver": "Network", "host": "192.168.1.80", "port": "9100"}})
    w, _, _ = asistente(config=config, impresora=impresora)
    w.choose_address()
    w.submit_address("192.168.1.80")

    assert w.step == pw.STEP_PROBLEM
    assert "Caja" in w.message
    assert impresora.pruebas == []


def test_un_nombre_repetido_se_explica_en_el_mismo_paso():
    config = ConfigFalso({"Cocina": {"driver": "Win32Raw", "printer_name": "EPSON"}})
    w, _, _ = asistente(config=config)
    w.choose_address()
    w.submit_address("192.168.1.80")
    w.confirm_paper(True)

    w.save("cocina")
    assert w.step == pw.STEP_NAME
    assert "Cocina" in w.message

    w.save("Barra")
    assert w.step == pw.STEP_SAVED


# ---------------------------------------------------------------------------
# "Configurar después" y resultados que llegan tarde
# ---------------------------------------------------------------------------

class RunnerDiferido:
    """Guarda las operaciones para terminarlas cuando el test quiera."""

    def __init__(self):
        self.pendientes = []

    def __call__(self, fn, on_done):
        self.pendientes.append((fn, on_done))

    def terminar_todo(self):
        while self.pendientes:
            fn, on_done = self.pendientes.pop(0)
            on_done(fn())


def test_configurar_despues_en_cualquier_paso():
    for preparar in (lambda w: None,
                     lambda w: w.choose_address(),
                     lambda w: (w.choose_address(), w.submit_address("192.168.1.80"))):
        w, reg, config = asistente()
        preparar(w)
        w.skip()
        assert reg.salidas == [pw.EXIT_SKIPPED]
        assert config.writes == []


def test_configurar_despues_con_una_guardada_cuenta_como_terminado():
    w, reg, _ = asistente()
    w.choose_address()
    w.submit_address("192.168.1.80")
    w.confirm_paper(True)
    w.save("Cocina")
    w.skip()
    assert reg.salidas == [pw.EXIT_FINISHED]


def test_un_resultado_que_llega_despues_de_salir_se_descarta():
    runner = RunnerDiferido()
    impresora = Impresora(ok)
    w, reg, _ = asistente(runner=runner, impresora=impresora)
    w.choose_address()
    w.submit_address("192.168.1.80")
    assert w.busy is True

    w.skip()                  # la persona se fue mientras se diagnosticaba
    runner.terminar_todo()    # el diagnóstico termina igual, tarde

    assert reg.salidas == [pw.EXIT_SKIPPED]
    assert w.busy is False
    assert impresora.pruebas == []   # no se imprimió nada después de salir
    assert w.result is None


def test_mientras_se_prueba_se_marca_ocupado():
    runner = RunnerDiferido()
    w, _, _ = asistente(runner=runner)
    w.choose_address()
    w.submit_address("192.168.1.80")
    assert w.busy is True

    runner.terminar_todo()
    assert w.busy is False
    assert w.step == pw.STEP_CONFIRM


def test_salir_cancela_lo_pendiente_en_la_cola_de_windows():
    class Tracker:
        cancelado = 0

        def cancel(self):
            Tracker.cancelado += 1
            return True

    resultado = PrintTestResult(technical_success=True, tracker=Tracker())
    w, _, _ = asistente(impresora=Impresora(resultado))
    w.test_candidate(PrinterCandidate.windows_queue("EPSON TM-T20"))
    assert w.step == pw.STEP_CONFIRM

    w.skip()
    assert Tracker.cancelado == 1


def test_volver():
    w, _, _ = asistente()
    w.choose_address()
    w.back()
    assert w.step == pw.STEP_INTRO

    w.choose_address()
    w.submit_address("192.168.1.80")
    w.confirm_paper(True)
    w.back()
    assert w.step == pw.STEP_CONFIRM


# ---------------------------------------------------------------------------
# La pantalla real (Kivy), sin ventana
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
        s = pss.PrinterSetupScreen(name="printer_setup")
        w, _, config = asistente(impresora=Impresora(ok))
        w.on_change = s._sync
        w.on_exit = s._exit
        s.wizard = w
        yield s, app, config
    finally:
        Builder.unload_file(kv)


def test_la_pantalla_sigue_los_pasos_del_asistente(pantalla):
    s, app, config = pantalla

    s.on_pre_enter()
    assert s.ids.pasos.current == "inicio"

    s.choose_address()
    assert s.ids.pasos.current == "direccion"

    s.submit_address("192.168.1.80")
    assert s.ids.pasos.current == "confirmar"
    assert s.test_code == s.wizard.test_code != ""

    s.confirm_paper(True)
    assert s.ids.pasos.current == "nombre"
    assert s.ids.alias.text == "Impresora"

    s.save("Cocina")
    assert s.ids.pasos.current == "guardada"
    assert s.saved == ["Cocina"]
    assert config.writes == ["Cocina"]

    s.finish()
    assert app.salidas == [pw.EXIT_FINISHED]


def test_la_pantalla_muestra_el_error_y_configurar_despues_sale(pantalla):
    s, app, _ = pantalla
    s.on_pre_enter()
    s.choose_address()
    s.submit_address("no-es-una-ip")

    assert s.ids.pasos.current == "direccion"
    assert s.message

    s.skip()
    assert app.salidas == [pw.EXIT_SKIPPED]
