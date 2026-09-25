"""
Pantalla del asistente de impresoras (#173).

Solo dibuja el recorrido de common/printer_wizard.py y le pasa las acciones:
toda la lógica vive allá, sin Kivy, y se prueba sin interfaz. Lo lento (red,
ticket de prueba) corre en un hilo aparte y vuelve al hilo de Kivy con Clock.

Salir del asistente ("Configurar después" o "Terminar") nunca detiene el
servicio de impresión, y cerrar la ventana en medio del recorrido la oculta en
la bandeja (#187): al volver a abrir Fiscalberry se sigue en el mismo paso.
"""

import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.uix.screenmanager import Screen

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.printer_wizard import STEP_INTRO, PrinterWizard, _capturar

logger = getLogger("GUI.PrinterSetup")


def kivy_runner(fn, on_done):
    """Corre `fn` en un hilo y entrega el resultado en el hilo de Kivy."""
    def trabajo():
        resultado = _capturar(fn)
        Clock.schedule_once(lambda _dt: on_done(resultado), 0)

    threading.Thread(target=trabajo, daemon=True, name="fiscalberry-asistente").start()


class PrinterSetupScreen(Screen):
    step = StringProperty(STEP_INTRO)
    message = StringProperty("")
    busy = BooleanProperty(False)
    test_code = StringProperty("")
    suggested_alias = StringProperty("")
    saved = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.wizard = None

    def _crear_asistente(self):
        from fiscalberry.common.Configberry import Configberry
        from fiscalberry.common.printer_setup import PrinterSetupService

        app = App.get_running_app()
        comercio = ""
        if app is not None:
            comercio = app.siteName or app.siteAlias or ""
        return PrinterWizard(
            PrinterSetupService(Configberry()),
            commerce=comercio,
            runner=kivy_runner,
            on_change=self._sync,
            on_exit=self._exit,
        )

    def ensure_wizard(self):
        if self.wizard is None:
            self.wizard = self._crear_asistente()
        return self.wizard

    def open_fresh(self):
        """Entrada desde la pantalla principal o la bandeja: desde el inicio."""
        self.ensure_wizard().start()

    def on_pre_enter(self, *args):
        # Volver a esta pantalla (por ejemplo, tras ocultar la ventana) retoma
        # el paso en el que estaba.
        self.ensure_wizard()
        self._sync()

    def _sync(self):
        w = self.wizard
        if w is None:
            return
        self.step = w.step
        self.message = w.message
        self.busy = w.busy
        self.test_code = w.test_code
        self.suggested_alias = w.suggested_alias
        self.saved = list(w.saved)
        pasos = self.ids.get("pasos") if hasattr(self, "ids") else None
        if pasos is not None and pasos.has_screen(w.step):
            pasos.current = w.step

    def _exit(self, motivo):
        app = App.get_running_app()
        if app is not None and hasattr(app, "leave_printer_setup"):
            app.leave_printer_setup(motivo)

    # -- acciones de la interfaz (delegan en el asistente) ----------------

    def choose_address(self):
        self.ensure_wizard().choose_address()

    def submit_address(self, texto):
        self.ensure_wizard().submit_address(texto)

    def confirm_paper(self, salio):
        self.ensure_wizard().confirm_paper(salio)

    def save(self, alias):
        self.ensure_wizard().save(alias)

    def retry(self):
        self.ensure_wizard().retry()

    def back(self):
        self.ensure_wizard().back()

    def add_another(self):
        self.ensure_wizard().add_another()

    def finish(self):
        self.ensure_wizard().finish()

    def skip(self):
        self.ensure_wizard().skip()
