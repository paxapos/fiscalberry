# coding=utf-8
"""
Tests del circuit breaker por impresora (Fase 8). Lógica pura, sin MQTT.
"""

from fiscalberry.common.printer_circuit_breaker import (
    PrinterCircuitBreaker, CircuitOpenError, CLOSED, OPEN, HALF_OPEN)


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, secs):
        self.t += secs


def test_starts_closed_and_allows():
    cb = PrinterCircuitBreaker(failure_threshold=3, cooldown=60)
    assert cb.state("p1") == CLOSED
    assert cb.allow("p1") is True


def test_opens_after_threshold_failures():
    clock = FakeClock()
    cb = PrinterCircuitBreaker(failure_threshold=3, cooldown=60, time_fn=clock)
    cb.record_failure("p1")
    cb.record_failure("p1")
    assert cb.state("p1") == CLOSED  # aún no llega al umbral
    cb.record_failure("p1")
    assert cb.state("p1") == OPEN
    assert cb.allow("p1") is False


def test_half_open_after_cooldown_then_success_closes():
    clock = FakeClock()
    cb = PrinterCircuitBreaker(failure_threshold=1, cooldown=30, time_fn=clock)
    cb.record_failure("p1")  # abre (threshold=1)
    assert cb.allow("p1") is False

    clock.advance(30)  # pasa cooldown
    assert cb.allow("p1") is True          # half_open: permite un intento
    cb.record_success("p1")
    assert cb.state("p1") == CLOSED
    assert cb.allow("p1") is True


def test_half_open_failure_reopens_and_resets_cooldown():
    clock = FakeClock()
    cb = PrinterCircuitBreaker(failure_threshold=1, cooldown=30, time_fn=clock)
    cb.record_failure("p1")            # abre
    clock.advance(30)
    assert cb.allow("p1") is True      # half_open
    cb.record_failure("p1")           # el intento de prueba falla -> reabre
    assert cb.allow("p1") is False     # cooldown reiniciado
    clock.advance(30)
    assert cb.allow("p1") is True      # vuelve a half_open


def test_success_resets_failure_counter():
    cb = PrinterCircuitBreaker(failure_threshold=3, cooldown=60)
    cb.record_failure("p1")
    cb.record_failure("p1")
    cb.record_success("p1")
    assert cb.failures("p1") == 0
    cb.record_failure("p1")
    assert cb.state("p1") == CLOSED  # el contador se reinició


def test_independent_state_per_printer():
    cb = PrinterCircuitBreaker(failure_threshold=1, cooldown=60)
    cb.record_failure("p1")
    assert cb.allow("p1") is False
    assert cb.allow("p2") is True


def test_circuit_open_error_is_exception():
    assert issubclass(CircuitOpenError, Exception)
