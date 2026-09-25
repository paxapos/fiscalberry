"""
Recorrido del asistente de impresoras (#173), sin Kivy.

Una máquina de pasos chica que la pantalla (ui/printer_setup_screen.py) solo
dibuja. Todo lo que puede demorar —el diagnóstico de red, el ticket de
prueba— corre fuera del hilo de la interfaz a través de `runner`, y un
resultado que llega tarde (la persona ya tocó "Configurar después" o volvió
atrás) se descarta.

Pasos:

    inicio ──> direccion ──> probando ──> confirmar ──> nombre ──> guardada
                   ^             │             │                     │
                   └──────── problema <────────┘            otra ────┘

- En la fase 1 la impresora se agrega por su dirección de red. La búsqueda
  automática (colas de Windows #174, red #175, USB/COM #183) se suma en la
  fase 2 sin cambiar el resto: todo buscador entrega PrinterCandidate a
  test_candidate(), que acepta cualquier transporte.
- Nada se guarda sin éxito técnico Y ticket confirmado en papel (#171/#172).
- "Configurar después" está disponible en todos los pasos y nunca detiene el
  servicio de impresión: el asistente no lo toca.
"""

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.printer_setup import (
    DEFAULT_RAW_PORT,
    DuplicatePrinterError,
    PrinterCandidate,
    SetupValidationError,
    TCP_INVALID,
    TCP_NO_RESPONSE,
    TCP_OK,
    TCP_REFUSED,
    probe_tcp,
)

logger = getLogger("PrinterWizard")

STEP_INTRO = "inicio"
STEP_ADDRESS = "direccion"
STEP_TESTING = "probando"
STEP_CONFIRM = "confirmar"
STEP_PROBLEM = "problema"
STEP_NAME = "nombre"
STEP_SAVED = "guardada"

EXIT_SKIPPED = "omitido"
EXIT_FINISHED = "terminado"

PROBE_MESSAGES = {
    TCP_REFUSED: (
        "En esa dirección responde un equipo, pero no recibe impresiones. "
        "Revisá que sea la dirección de la impresora."),
    TCP_NO_RESPONSE: (
        "Nadie respondió en esa dirección. Revisá que la impresora esté "
        "encendida, conectada a la red y que la dirección sea la correcta."),
    TCP_INVALID: "Esa dirección no es válida. Tiene que ser como 192.168.1.50.",
}

PAPER_NOT_PRINTED = (
    "El ticket no salió. Revisá que la impresora tenga papel y esté "
    "encendida, y probá de nuevo.")


def run_sync(fn, on_done):
    """Runner para tests: corre en el acto."""
    on_done(_capturar(fn))


def _capturar(fn):
    try:
        return fn()
    except Exception as e:  # el callback decide qué mostrar
        return e


class PrinterWizard:
    """
    Estado del recorrido. La interfaz lee `step`, `message`, `busy`,
    `test_code`, `suggested_alias` y `saved`, y llama a las acciones.
    `on_change()` avisa que algo cambió; `on_exit(motivo)` que hay que salir
    del asistente (EXIT_SKIPPED o EXIT_FINISHED).
    """

    def __init__(self, service, commerce="", runner=run_sync, probe=probe_tcp,
                 print_test=None, on_change=None, on_exit=None):
        self.service = service
        self.commerce = commerce
        self.runner = runner
        self.probe = probe
        self.print_test = print_test
        self.on_change = on_change
        self.on_exit = on_exit

        self.step = STEP_INTRO
        self.message = ""
        self.busy = False
        self.candidate = None
        self.result = None
        self.info = None
        self.suggested_alias = ""
        self.saved = []
        self._op = 0

    # -- utilidades -------------------------------------------------------

    @property
    def test_code(self):
        return self.info.code if self.info else ""

    def _go(self, step, message=""):
        self.step = step
        self.message = message
        self.busy = False
        self._changed()

    def _changed(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception as e:
                logger.error(f"Error actualizando la pantalla del asistente: {e}")

    def _async(self, fn, on_done):
        """Corre `fn` fuera del hilo de la interfaz; ignora respuestas viejas."""
        self._op += 1
        token = self._op
        self.busy = True
        self._changed()

        def listo(resultado):
            if token != self._op:
                logger.debug("Resultado descartado: la persona ya siguió de largo")
                return
            self.busy = False
            on_done(resultado)

        self.runner(fn, listo)

    def _descartar_pendiente(self):
        """Invalida la operación en curso y cancela lo que haya quedado en cola."""
        self._op += 1
        self.busy = False
        if self.result is not None and not self.result.can_save:
            self.result.cancel()

    # -- acciones ---------------------------------------------------------

    def start(self):
        self._descartar_pendiente()
        self.candidate = None
        self.result = None
        self.info = None
        self._go(STEP_INTRO)

    def choose_address(self):
        self._go(STEP_ADDRESS)

    def submit_address(self, host, port=DEFAULT_RAW_PORT):
        """Valida la dirección, la diagnostica (<= 3 s) y, si responde, prueba."""
        try:
            candidate = PrinterCandidate.network(host, port)
        except SetupValidationError as e:
            self._go(STEP_ADDRESS, str(e))
            return

        def diagnosticar():
            return self.probe(candidate.driver_config["host"],
                              int(candidate.driver_config["port"]))

        def listo(resultado):
            if isinstance(resultado, Exception):
                self._go(STEP_ADDRESS, PROBE_MESSAGES[TCP_NO_RESPONSE])
            elif resultado != TCP_OK:
                self._go(STEP_ADDRESS, PROBE_MESSAGES.get(resultado,
                                                          PROBE_MESSAGES[TCP_NO_RESPONSE]))
            else:
                self.test_candidate(candidate)

        self.message = ""
        self._async(diagnosticar, listo)

    def test_candidate(self, candidate):
        """Imprime el ticket de prueba de un candidato (cualquier transporte)."""
        duplicada = self.service.find_duplicate(candidate)
        if duplicada is not None:
            self._go(STEP_PROBLEM,
                     f"Esta impresora ya está configurada como \"{duplicada}\". "
                     "No hace falta volver a agregarla.")
            self.candidate = None
            return

        from fiscalberry.common.printer_test import ACTIONS, PrintTestInfo, run_print_test

        self.candidate = candidate
        self.result = None
        self.info = PrintTestInfo.for_candidate(
            candidate, commerce=self.commerce, alias=self.service.suggest_alias())
        imprimir = self.print_test or run_print_test
        self.step = STEP_TESTING
        self.message = ""

        def listo(resultado):
            if isinstance(resultado, Exception):
                logger.error(f"La prueba de impresión falló inesperadamente: {resultado}")
                self._go(STEP_PROBLEM, "No se pudo imprimir la prueba. Probá de nuevo.")
                return
            self.result = resultado
            if resultado.technical_success:
                # Un aviso (poco papel) no impide seguir, pero se muestra.
                self._go(STEP_CONFIRM, ACTIONS.get(resultado.warning, ""))
            else:
                self._go(STEP_PROBLEM, resultado.action or "")

        self._async(lambda: imprimir(candidate, self.info), listo)

    def retry(self):
        if self.candidate is not None:
            self.test_candidate(self.candidate)
        else:
            self.start()

    def confirm_paper(self, printed):
        if self.result is None or self.step != STEP_CONFIRM:
            return
        if self.result.confirm_paper(printed):
            self.suggested_alias = self.service.suggest_alias()
            self._go(STEP_NAME)
        else:
            self._go(STEP_PROBLEM, PAPER_NOT_PRINTED)

    def save(self, alias):
        if self.result is None or not self.result.can_save:
            self._go(STEP_PROBLEM, "Primero hay que probar la impresora.")
            return
        try:
            guardada = self.service.save_confirmed(
                alias, self.candidate,
                technical_success=self.result.technical_success,
                physical_confirmed=self.result.paper_confirmed,
            )
        except DuplicatePrinterError as e:
            self._go(STEP_NAME, str(e))
            return
        except SetupValidationError as e:
            self._go(STEP_NAME, str(e))
            return
        except Exception as e:
            logger.error(f"No se pudo guardar la impresora: {e}", exc_info=True)
            self._go(STEP_NAME, "No se pudo guardar la impresora. Probá de nuevo.")
            return
        logger.info("Impresora '%s' guardada desde el asistente (%s)",
                    guardada, self.candidate.stable_id)
        self.saved.append(guardada)
        self.result = None
        self._go(STEP_SAVED)

    def add_another(self):
        self.start()

    def back(self):
        if self.step in (STEP_ADDRESS, STEP_PROBLEM, STEP_SAVED):
            self.start()
        elif self.step == STEP_NAME:
            # Volver desde el nombre no deshace la prueba: se puede guardar
            # después. Pero no se deja un resultado confirmado colgando.
            self._go(STEP_CONFIRM)
        elif self.step == STEP_CONFIRM:
            self.start()
        elif self.step == STEP_TESTING:
            self.start()

    def skip(self):
        """"Configurar después": se sale sin guardar lo que no se confirmó."""
        self._descartar_pendiente()
        self._salir(EXIT_SKIPPED if not self.saved else EXIT_FINISHED)

    def finish(self):
        self._descartar_pendiente()
        self._salir(EXIT_FINISHED)

    def _salir(self, motivo):
        if self.on_exit:
            self.on_exit(motivo)
