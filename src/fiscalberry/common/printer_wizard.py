"""
Recorrido del asistente de impresoras (#173, #184), sin Kivy.

Una máquina de pasos chica que la pantalla (ui/printer_setup_screen.py) solo
dibuja. Todo lo que puede demorar —la búsqueda, el diagnóstico de red, el
ticket de prueba— corre fuera del hilo de la interfaz a través de `runner`,
y un resultado que llega tarde (la persona ya tocó "Configurar después" o
volvió atrás) se descarta.

Pasos:

    inicio ──> resultados ──> probando ──> confirmar ──> nombre ──> guardada
      │            │  ^            │             │                     │
      │            v  │            v             v                     │
      └──────> direccion ──────> problema <──────┘       agregar otra ─┘

- "Buscar impresoras" corre en paralelo red (#175), USB/COM (#183) y colas
  de Windows (#174) y muestra todo en un solo listado, que se va llenando a
  medida que cada fuente termina (PrinterSearch).
- "Sé la dirección" queda para una impresora de red que no apareció: se
  diagnostica con la máscara real de la PC y, si está en otra red, se explica
  por qué. Solo se explica: no se cambia nada, ni se abren guías.
- Todo candidato, venga de donde venga, se prueba con el ticket de #172.
- Nada se guarda sin éxito técnico Y ticket confirmado en papel (#171/#172).
  Si la prueba no se confirma, lo pendiente se descarta (en una cola de
  Windows, el trabajo se borra: no queda un "ticket fantasma").
- "Configurar después" está disponible en todos los pasos y nunca detiene el
  servicio de impresión: el asistente no lo toca.
- `journal` registra cada paso con su resultado, para el diagnóstico de
  soporte (#185).

Diseño portado de feat/instalador-v3 (PR #189) y adaptado a ticket_prueba.
"""

import dataclasses
import threading
import time

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.printer_setup import (
    PUERTO_RAW,
    DuplicatePrinterError,
    PrinterCandidate,
    SetupValidationError,
    TCP_INVALIDO,
    TCP_RECHAZADO,
    TCP_SIN_RESPUESTA,
    probe_tcp,
)

logger = getLogger("PrinterWizard")

STEP_INTRO = "inicio"
STEP_RESULTS = "resultados"
STEP_ADDRESS = "direccion"
STEP_TESTING = "probando"
STEP_CONFIRM = "confirmar"
STEP_PROBLEM = "problema"
STEP_NAME = "nombre"
STEP_SAVED = "guardada"

EXIT_SKIPPED = "omitido"
EXIT_FINISHED = "terminado"

PROBE_MESSAGES = {
    TCP_RECHAZADO: (
        "En esa dirección responde un equipo, pero no recibe impresiones. "
        "Revisá que sea la dirección de la impresora."),
    TCP_SIN_RESPUESTA: (
        "Nadie respondió en esa dirección. Revisá que la impresora esté "
        "encendida, conectada a la red y que la dirección sea la correcta."),
    TCP_INVALIDO: "Esa dirección no es válida. Tiene que ser como 192.168.1.50.",
}

GATEWAY_MESSAGE = ("Esa es la dirección del router, no de la impresora. Buscá la "
                   "dirección en el ticket de configuración de la impresora.")

ALREADY_CONFIGURED = ("Esta impresora ya está configurada como \"{}\". "
                      "No hace falta volver a agregarla.")

PAPER_NOT_PRINTED = (
    "El ticket no salió. Revisá que la impresora tenga papel y esté "
    "encendida, y probá de nuevo.")

NOTHING_FOUND = (
    "No encontramos impresoras. Revisá que esté encendida y conectada (cable "
    "USB o cable de red al router) y tocá \"Buscar de nuevo\".")

SEARCH_FAILED = "No se pudo buscar impresoras. Probá de nuevo."
TEST_FAILED = "No se pudo imprimir la prueba. Probá de nuevo."
NOT_TESTED = "Primero hay que probar la impresora."
SAVE_FAILED = "No se pudo guardar la impresora. Probá de nuevo."

JOURNAL_LIMIT = 200


def run_sync(fn, on_done):
    """Runner para tests: corre en el acto."""
    on_done(capturar(fn))


def capturar(fn):
    try:
        return fn()
    except Exception as e:  # el callback decide qué mostrar
        return e


def _en_el_acto(fn):
    fn()


def _red_de(diagnostico):
    """"192.168.1.x" para explicar en qué red está la PC."""
    if not diagnostico.local_networks:
        return ""
    red = diagnostico.local_networks[0]
    base, _, prefijo = red.partition("/")
    if prefijo == "24":
        return base.rsplit(".", 1)[0] + ".x"
    return red


def diagnosis_message(d):
    """El motivo, en palabras, por el que una dirección no se puede usar tal cual."""
    from fiscalberry.common import network_discovery as nd

    if d.kind == nd.KIND_INVALID:
        return d.error or PROBE_MESSAGES[TCP_INVALIDO]
    if d.kind == nd.KIND_PORT_CLOSED:
        return GATEWAY_MESSAGE if d.is_gateway else PROBE_MESSAGES[TCP_RECHAZADO]
    if d.kind == nd.KIND_HOST_OFF:
        return PROBE_MESSAGES[TCP_SIN_RESPUESTA]
    red = _red_de(d)
    if d.kind == nd.KIND_OTHER_KNOWN:
        marcas = " / ".join(d.brands)
        return (f"La impresora tiene la dirección de fábrica de {marcas}, que es de otra "
                f"red{f' (esta computadora está en {red})' if red else ''}. Hay que "
                "ponerla en la red del local con la herramienta del fabricante.")
    if d.kind == nd.KIND_OTHER_UNKNOWN:
        return ("Esa dirección es de otra red"
                + (f": esta computadora está en {red}" if red else "")
                + ". La impresora tiene que tener una dirección de la misma red.")
    return PROBE_MESSAGES[TCP_SIN_RESPUESTA]


def _probar(candidato, alias, comercio, codigo):
    from fiscalberry.common.ticket_prueba import probar
    return probar(candidato, alias, comercio=comercio, codigo=codigo)


class PrinterWizard:
    """
    Estado del recorrido. La interfaz lee `step`, `message`, `busy`,
    `searching`, `found`, `show_all`, `notes`, `test_code`, `suggested_alias`
    y `saved`, y llama a las acciones. `on_change()` avisa que algo cambió;
    `on_exit(motivo)` que hay que salir del asistente (EXIT_SKIPPED o
    EXIT_FINISHED). `post(fn)` lleva una función al hilo de la interfaz (para
    los resultados parciales de la búsqueda).
    """

    def __init__(self, service, commerce="", runner=run_sync, probe=probe_tcp,
                 print_test=_probar, on_change=None, on_exit=None, search=None,
                 post=_en_el_acto, diagnose=None, list_adapters=None, clock=time.time,
                 new_code=None):
        self.service = service
        self.commerce = commerce
        self.runner = runner
        self.probe = probe
        self.print_test = print_test
        self.on_change = on_change
        self.on_exit = on_exit
        self.post = post
        self._search_fn = search
        self._diagnose_fn = diagnose
        self._list_adapters = list_adapters
        self.clock = clock
        if new_code is None:
            from fiscalberry.common.ticket_prueba import nuevo_codigo as new_code
        self._new_code = new_code

        self.step = STEP_INTRO
        self.message = ""
        self.busy = False
        self.candidate = None
        self.result = None
        self.last_result = None   # la última prueba, aunque ya se haya guardado (#185)
        self.test_code = ""
        self.paper_confirmed = False
        self.suggested_alias = ""
        self.saved = []
        self.search_result = None
        self.searching = False
        self.show_all = False
        self.diagnosis = None
        self.address = ""         # la dirección escrita a mano (#185)
        self.journal = []
        self._desde_busqueda = False
        self._cancel = None
        self._op = 0

    # -- utilidades -------------------------------------------------------

    @property
    def found(self):
        """Lo que se muestra en la lista (según "Mostrar todas")."""
        if self.search_result is None:
            return []
        return self.search_result.visible(self.show_all)

    @property
    def hidden_count(self):
        return self.search_result.hidden_count if self.search_result is not None else 0

    @property
    def notes(self):
        return list(self.search_result.notes) if self.search_result is not None else []

    def _registrar(self, evento, **datos):
        self.journal.append(dict(t=round(self.clock(), 3), paso=self.step, evento=evento, **datos))
        del self.journal[:-JOURNAL_LIMIT]

    def _go(self, step, message=""):
        self.step = step
        self.message = message
        self.busy = False
        self._registrar("paso", mensaje=message)
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

    def _cancelar_busqueda(self):
        if self._cancel is not None:
            self._cancel.set()
            self._cancel = None
        self.searching = False

    def _descartar_prueba(self):
        """
        Una prueba que no se confirmó en papel no deja nada pendiente: en una
        cola de Windows, el trabajo se borra para que no salga solo después.
        """
        if self.result is not None and not self.paper_confirmed:
            try:
                self.result.descartar()
            except Exception as e:
                logger.warning(f"No se pudo descartar la prueba: {e}")
        self.result = None
        self.paper_confirmed = False

    def _descartar_pendiente(self):
        """Invalida la operación en curso y cancela lo que haya quedado."""
        self._op += 1
        self.busy = False
        self._cancelar_busqueda()
        self._descartar_prueba()

    def _volver(self):
        """Adonde se vuelve desde un problema: la lista, si se vino de ahí."""
        if self._desde_busqueda and self.search_result is not None:
            self._descartar_pendiente()
            self._remarcar()
            self.candidate = None
            self._go(STEP_RESULTS)
        else:
            self.start()

    def _remarcar(self):
        """Marca en la lista las que se acaban de guardar."""
        if self.search_result is None:
            return
        from fiscalberry.common.printer_search import merge
        r = self.search_result
        r.found, r.notes = merge(r.network, r.usb, r.queues, self.service)

    # -- inicio -------------------------------------------------------------

    def start(self):
        self._descartar_pendiente()
        self.candidate = None
        self.test_code = ""
        self._desde_busqueda = False
        self._go(STEP_INTRO)

    # -- búsqueda (#184) ----------------------------------------------------

    def _buscador(self):
        if self._search_fn is not None:
            return self._search_fn
        from fiscalberry.common.printer_search import PrinterSearch
        return PrinterSearch(self.service).run

    def search(self):
        """"Buscar impresoras": red, USB/COM y colas de Windows a la vez."""
        self._descartar_pendiente()
        cancel = threading.Event()
        self._cancel = cancel
        self.search_result = None
        self.searching = True
        self.show_all = False
        self.candidate = None
        self._desde_busqueda = True
        self._go(STEP_RESULTS)
        token = self._op + 1   # el que va a usar _async
        buscar = self._buscador()

        def parcial(resultado):
            def mostrar():
                if token != self._op or cancel.is_set():
                    return
                self.search_result = resultado
                self._changed()
            self.post(mostrar)

        def listo(resultado):
            self.searching = False
            if self._cancel is cancel:
                self._cancel = None
            if isinstance(resultado, Exception):
                logger.error(f"La búsqueda de impresoras falló: {resultado}")
                self._go(STEP_RESULTS, SEARCH_FAILED)
                return
            self.search_result = resultado
            self._registrar("busqueda", encontradas=len(resultado.found),
                            ocultas=resultado.hidden_count, segundos=round(resultado.seconds, 1),
                            avisos=list(resultado.notes))
            self._go(STEP_RESULTS, "" if resultado.visible(False) else NOTHING_FOUND)

        self._async(lambda: buscar(cancel=cancel, on_partial=parcial), listo)

    def cancel_search(self):
        """Deja de buscar y muestra lo que se encontró hasta ahora."""
        if not self.searching:
            return
        self._op += 1
        self._cancelar_busqueda()
        self.busy = False
        self._go(STEP_RESULTS, "" if self.found else NOTHING_FOUND)

    def toggle_show_all(self):
        self.show_all = not self.show_all
        self._changed()

    def choose_found(self, key):
        """La persona eligió una impresora del listado."""
        from fiscalberry.common.printer_search import find

        elegida = find(self.search_result.found if self.search_result else [], key)
        if elegida is None:
            return
        self._registrar("eligio", clave=key, conexion=elegida.connection)
        if self.searching:
            # Se deja de buscar para no competir con la prueba; lo encontrado queda.
            self._op += 1
            self._cancelar_busqueda()
        self._desde_busqueda = True
        if elegida.configured_as:
            self._go(STEP_PROBLEM, ALREADY_CONFIGURED.format(elegida.configured_as))
            return
        if elegida.candidate is None:
            self._go(STEP_PROBLEM, elegida.note)
            return
        self.test_candidate(elegida.candidate)

    # -- dirección escrita a mano -------------------------------------------

    def choose_address(self):
        self._desde_busqueda = self.step == STEP_RESULTS or self._desde_busqueda
        if self.searching:
            self._op += 1
            self._cancelar_busqueda()
        self._go(STEP_ADDRESS)

    def _adaptadores(self):
        r = self.search_result
        if r is not None and r.network is not None and r.network.adapters:
            return r.network.adapters
        if self._list_adapters is not None:
            return self._list_adapters()
        from fiscalberry.common.network_discovery import list_adapters
        return list_adapters()

    def _diagnosticar(self, host, port):
        if self._diagnose_fn is not None:
            return self._diagnose_fn(host, port)
        from fiscalberry.common.network_discovery import diagnose_address
        try:
            adaptadores = self._adaptadores()
        except Exception as e:
            logger.warning(f"No se pudieron leer los adaptadores de red: {e}")
            adaptadores = []
        return diagnose_address(host, port, adapters=adaptadores, probe=self.probe)

    def submit_address(self, host, port=PUERTO_RAW):
        """Valida la dirección, la diagnostica (<= 3 s) y, si responde, prueba."""
        self.address = str(host or "").strip()
        try:
            candidate = PrinterCandidate.network(host, port)
        except SetupValidationError as e:
            self._go(STEP_ADDRESS, str(e))
            return

        def listo(resultado):
            if isinstance(resultado, Exception):
                logger.error(f"El diagnóstico de la dirección falló: {resultado}")
                self._go(STEP_ADDRESS, PROBE_MESSAGES[TCP_SIN_RESPUESTA])
                return
            self.diagnosis = resultado
            self._registrar("diagnostico", **resultado.as_dict())
            if resultado.printable:
                self.test_candidate(candidate)
            else:
                self._go(STEP_ADDRESS, diagnosis_message(resultado))

        self.message = ""
        host_ok = candidate.driver_config["host"]
        port_ok = int(candidate.driver_config["port"])
        self._async(lambda: self._diagnosticar(host_ok, port_ok), listo)

    # -- la prueba ------------------------------------------------------------

    def test_candidate(self, candidate):
        """Imprime el ticket de prueba de un candidato (cualquier conexión)."""
        self._descartar_prueba()
        duplicada = self.service.buscar_duplicado(candidate)
        if duplicada is not None:
            self.candidate = None
            self._go(STEP_PROBLEM, ALREADY_CONFIGURED.format(duplicada))
            return

        self.candidate = candidate
        self.last_result = None
        self.test_code = self._new_code()
        # El ticket dice el nombre que se le va a proponer; la persona lo
        # puede cambiar después.
        alias = self.service.sugerir_nombre()
        codigo = self.test_code
        self.step = STEP_TESTING
        self.message = ""
        self._registrar("prueba", conexion=candidate.connection, identidad=candidate.stable_id)

        def listo(resultado):
            if isinstance(resultado, Exception):
                logger.error(f"La prueba de impresión falló inesperadamente: {resultado}")
                self._registrar("resultado", error=str(resultado))
                self._go(STEP_PROBLEM, TEST_FAILED)
                return
            self.result = resultado
            self.last_result = resultado
            self.paper_confirmed = False
            estado = resultado.estado_despues or resultado.estado_antes
            self._registrar("resultado", tecnico=resultado.exito_tecnico,
                            problema=resultado.problema, avisos=list(resultado.avisos),
                            estado=dataclasses.asdict(estado) if estado else None,
                            lpt=dict(resultado.lpt), detalle=resultado.detalle)
            if resultado.exito_tecnico:
                # Un aviso (poco papel) no impide seguir, pero se muestra.
                self._go(STEP_CONFIRM, " ".join(resultado.avisos))
            else:
                self._go(STEP_PROBLEM, resultado.accion or TEST_FAILED)

        self._async(lambda: self.print_test(candidate, alias, self.commerce, codigo), listo)

    def retry(self):
        if self.candidate is not None:
            self.test_candidate(self.candidate)
        elif self._desde_busqueda and self.search_result is not None:
            self.search()
        else:
            self.start()

    def confirm_paper(self, printed):
        if self.result is None or self.step != STEP_CONFIRM:
            return
        self._registrar("papel", salio=bool(printed))
        if printed:
            self.paper_confirmed = True
            self.suggested_alias = self.service.sugerir_nombre()
            self._go(STEP_NAME)
        else:
            self._descartar_prueba()
            self._go(STEP_PROBLEM, PAPER_NOT_PRINTED)

    def save(self, alias):
        from fiscalberry.common.ticket_prueba import finalizar

        if self.result is None or not self.result.exito_tecnico or not self.paper_confirmed:
            self._go(STEP_PROBLEM, NOT_TESTED)
            return
        try:
            guardada = finalizar(self.service, alias, self.candidate, self.result,
                                 salio_en_papel=True)
        except (DuplicatePrinterError, SetupValidationError) as e:
            self._go(STEP_NAME, str(e))
            return
        except Exception as e:
            logger.error(f"No se pudo guardar la impresora: {e}", exc_info=True)
            self._go(STEP_NAME, SAVE_FAILED)
            return
        logger.info("Impresora '%s' guardada desde el asistente (%s)",
                    guardada, self.candidate.stable_id)
        self.saved.append(guardada)
        self._registrar("guardada", nombre=guardada, conexion=self.candidate.connection)
        self.result = None
        self.paper_confirmed = False
        self._go(STEP_SAVED)

    def add_another(self):
        if self._desde_busqueda and self.search_result is not None:
            self._volver()
        else:
            self.start()

    def back(self):
        if self.step == STEP_RESULTS:
            self.start()
        elif self.step == STEP_ADDRESS:
            if self._desde_busqueda and self.search_result is not None:
                self._volver()
            else:
                self.start()
        elif self.step == STEP_NAME:
            # Volver desde el nombre no deshace la prueba: el papel ya se
            # confirmó y se puede guardar después.
            self._go(STEP_CONFIRM)
        elif self.step in (STEP_PROBLEM, STEP_CONFIRM, STEP_TESTING):
            self._volver()
        elif self.step == STEP_SAVED:
            self.start()

    def skip(self):
        """"Configurar después": se sale sin guardar lo que no se confirmó."""
        motivo = EXIT_FINISHED if self.saved else EXIT_SKIPPED
        self._descartar_pendiente()
        self._registrar("salida", motivo=motivo)
        self._salir(motivo)

    def finish(self):
        self._descartar_pendiente()
        self._registrar("salida", motivo=EXIT_FINISHED)
        self._salir(EXIT_FINISHED)

    def _salir(self, motivo):
        if self.on_exit:
            self.on_exit(motivo)
