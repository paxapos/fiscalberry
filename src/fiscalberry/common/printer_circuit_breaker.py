# coding=utf-8
"""
Circuit breaker por impresora (Fase 8).

Evita martillar el driver de una impresora que falla repetidamente. Complementa
al spooler durable: el spooler ya reintenta con backoff, y el breaker agrega un
corte explícito por impresora con estados closed/open/half_open, de modo que
mientras una impresora está "caída" no se intenta imprimir en cada ciclo, y el
reporte de error puede rate-limitarse por ventana.

Estados:
  - closed:    funciona normal; los fallos consecutivos incrementan el contador.
  - open:      tras `failure_threshold` fallos consecutivos; se rechazan intentos
               hasta que pase `cooldown` segundos.
  - half_open: pasado el cooldown, se permite UN intento de prueba. Si sale OK,
               vuelve a closed; si falla, vuelve a open y reinicia el cooldown.

Es thread-safe. El tiempo es inyectable (`time_fn`) para tests deterministas.
"""

import threading
import time as _time

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Se lanza cuando el circuito de una impresora está abierto."""


class PrinterCircuitBreaker:
    def __init__(self, failure_threshold=5, cooldown=60.0, time_fn=None):
        self._failure_threshold = int(failure_threshold)
        self._cooldown = float(cooldown)
        self._time = time_fn or _time.monotonic
        self._lock = threading.Lock()
        # printer_name -> {"failures": int, "state": str, "opened_at": float}
        self._state = {}

    def _entry(self, printer_name):
        e = self._state.get(printer_name)
        if e is None:
            e = {"failures": 0, "state": CLOSED, "opened_at": 0.0}
            self._state[printer_name] = e
        return e

    def allow(self, printer_name):
        """True si se permite intentar imprimir en esta impresora ahora."""
        with self._lock:
            e = self._entry(printer_name)
            if e["state"] == OPEN:
                if (self._time() - e["opened_at"]) >= self._cooldown:
                    # Pasó el cooldown: permitir un intento de prueba.
                    e["state"] = HALF_OPEN
                    return True
                return False
            # closed o half_open -> permitido
            return True

    def record_success(self, printer_name):
        """Registra impresión OK: cierra el circuito y resetea el contador."""
        with self._lock:
            e = self._entry(printer_name)
            e["failures"] = 0
            e["state"] = CLOSED
            e["opened_at"] = 0.0

    def record_failure(self, printer_name):
        """Registra fallo: abre el circuito si se supera el umbral."""
        with self._lock:
            e = self._entry(printer_name)
            if e["state"] == HALF_OPEN:
                # El intento de prueba falló: reabrir y reiniciar cooldown.
                e["state"] = OPEN
                e["opened_at"] = self._time()
                return
            e["failures"] += 1
            if e["failures"] >= self._failure_threshold:
                e["state"] = OPEN
                e["opened_at"] = self._time()

    def state(self, printer_name):
        """Estado actual (resuelve open->half_open si venció el cooldown)."""
        with self._lock:
            e = self._entry(printer_name)
            if e["state"] == OPEN and (self._time() - e["opened_at"]) >= self._cooldown:
                return HALF_OPEN
            return e["state"]

    def failures(self, printer_name):
        with self._lock:
            return self._entry(printer_name)["failures"]


# Singleton perezoso para uso en el spooler.
_breaker = None
_breaker_lock = threading.Lock()


def get_circuit_breaker():
    global _breaker
    if _breaker is None:
        with _breaker_lock:
            if _breaker is None:
                _breaker = PrinterCircuitBreaker()
    return _breaker
