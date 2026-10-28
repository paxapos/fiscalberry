# coding=utf-8
"""
Regresión: un trabajo que falla no puede darse por impreso.

Visto en un dispositivo real:

    Spooler: job remito-463-c0-55ccf67b encolado (impresora=comandera)
    ERROR Printer not found in configuration: 'comandera'
    Spooler: job remito-463-c0-55ccf67b impreso OK      <-- mentira

runTraductor no siempre lanza: ante "impresora no encontrada" o config inválida
DEVUELVE {"error": ...}. El spooler solo entiende excepciones, así que marcaba
el trabajo como impreso y lo descartaba: el ticket se perdía en silencio y no se
reintentaba ni después de configurar la impresora. En un POS eso es una comanda
que nunca sale y nadie se entera.
"""

import pytest

from fiscalberry.common import ComandosHandler as ch


@pytest.fixture
def sin_circuit_breaker(monkeypatch):
    """El breaker no debe interferir: siempre permite y registra sin efecto."""

    class BreakerPermisivo:
        def __init__(self):
            self.fallos = []
            self.exitos = []

        def allow(self, _nombre):
            return True

        def record_failure(self, nombre):
            self.fallos.append(nombre)

        def record_success(self, nombre):
            self.exitos.append(nombre)

    breaker = BreakerPermisivo()
    monkeypatch.setattr(
        "fiscalberry.common.printer_circuit_breaker.get_circuit_breaker",
        lambda: breaker,
    )
    return breaker


def test_impresora_no_encontrada_es_un_fallo(monkeypatch, sin_circuit_breaker):
    monkeypatch.setattr(
        ch, "runTraductor", lambda *a, **k: {"error": "Impresora no encontrada: comandera"}
    )

    with pytest.raises(ch.PrintJobError, match="comandera"):
        ch._spooler_print_fn({"printerName": "comandera"})

    assert sin_circuit_breaker.fallos == ["comandera"], "debe contar como fallo de esa impresora"
    assert sin_circuit_breaker.exitos == []


def test_error_de_configuracion_es_un_fallo(monkeypatch, sin_circuit_breaker):
    monkeypatch.setattr(
        ch, "runTraductor", lambda *a, **k: {"error": "Error de configuración: falta host"}
    )

    with pytest.raises(ch.PrintJobError):
        ch._spooler_print_fn({"printerName": "cocina"})


def test_impresion_exitosa_sigue_siendo_exito(monkeypatch, sin_circuit_breaker):
    monkeypatch.setattr(
        ch, "runTraductor", lambda *a, **k: {"message": "Impresión exitosa", "result": "ok"}
    )

    resultado = ch._spooler_print_fn({"printerName": "cocina"})

    assert resultado["message"] == "Impresión exitosa"
    assert sin_circuit_breaker.exitos == ["cocina"]
    assert sin_circuit_breaker.fallos == []


def test_error_vacio_no_se_confunde_con_error(monkeypatch, sin_circuit_breaker):
    """Un 'error' vacío o None no debe hacer fallar un trabajo que salió bien."""
    monkeypatch.setattr(ch, "runTraductor", lambda *a, **k: {"error": "", "result": "ok"})

    ch._spooler_print_fn({"printerName": "cocina"})

    assert sin_circuit_breaker.exitos == ["cocina"]
