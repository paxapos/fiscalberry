"""
Pantalla del asistente de impresoras (#173, #184).

Solo dibuja el recorrido de common/printer_wizard.py y le pasa las acciones:
toda la lógica vive allá, sin Kivy, y se prueba sin interfaz. Lo lento
(búsqueda, red, ticket de prueba) corre en hilos aparte y vuelve al hilo de
Kivy con Clock.

- "Buscar impresoras" muestra red, USB/COM y colas de Windows en un solo
  listado que se va llenando. Cada fila dice qué es con palabras simples; IP,
  puerto y driver aparecen solo con "Ver detalles".
- Teclado: Tab / Shift+Tab recorren los botones y las impresoras, Enter o
  Espacio tocan el que tiene el foco, Escape vuelve atrás.
- Salir del asistente ("Configurar después" o "Terminar") nunca detiene el
  servicio de impresión, y cerrar la ventana en medio del recorrido la oculta
  en la bandeja (#187): al volver a abrir Fiscalberry se sigue en el mismo
  paso. Salir cancela la búsqueda en curso.
"""

import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior, FocusBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.screenmanager import Screen

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.printer_wizard import STEP_INTRO, PrinterWizard, _capturar

logger = getLogger("GUI.PrinterSetup")

TECLAS_ACTIVAR = ("enter", "numpadenter", "spacebar")
# Qué recibe el foco al llegar a cada paso (Enter lo toca o escribe ahí).
FOCO_INICIAL = {
    "inicio": "principal_inicio",
    "direccion": "direccion",
    "problema": "principal_problema",
    "nombre": "alias",
    "guardada": "principal_guardada",
}
TECLA_ESCAPE = 27


def kivy_runner(fn, on_done):
    """Corre `fn` en un hilo y entrega el resultado en el hilo de Kivy."""
    def trabajo():
        resultado = _capturar(fn)
        Clock.schedule_once(lambda _dt: on_done(resultado), 0)

    threading.Thread(target=trabajo, daemon=True, name="fiscalberry-asistente").start()


def armar_diagnostico(wizard):
    from fiscalberry.common.support_report import build_report
    return build_report(wizard)


def copiar_al_portapapeles(texto):
    from kivy.core.clipboard import Clipboard
    Clipboard.copy(texto)


def kivy_post(fn):
    """Lleva `fn` al hilo de Kivy (resultados parciales de la búsqueda)."""
    Clock.schedule_once(lambda _dt: fn(), 0)


class BotonFoco(FocusBehavior, Button):
    """Botón que se puede alcanzar con Tab y tocar con Enter o Espacio."""

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        if keycode[1] in TECLAS_ACTIVAR and not self.disabled:
            self.trigger_action(0)
            return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)


class ImpresoraItem(FocusBehavior, ButtonBehavior, BoxLayout):
    """Una impresora del listado: nombre grande, frase simple y detalles opcionales."""

    clave = StringProperty("")
    titulo = StringProperty("")
    subtitulo = StringProperty("")
    nota = StringProperty("")
    detalles = StringProperty("")
    configurada = StringProperty("")
    oculta_por = StringProperty("")
    seleccionable = BooleanProperty(True)
    mostrar_detalles = BooleanProperty(False)
    pantalla = ObjectProperty(None, allownone=True)

    def on_press(self):
        if self.pantalla is not None:
            self.pantalla.choose_found(self.clave)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        if keycode[1] in TECLAS_ACTIVAR:
            self.trigger_action(0)
            return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)


class PrinterSetupScreen(Screen):
    step = StringProperty(STEP_INTRO)
    message = StringProperty("")
    guide = StringProperty("")
    busy = BooleanProperty(False)
    searching = BooleanProperty(False)
    show_all = BooleanProperty(False)
    show_details = BooleanProperty(False)
    hidden_count = NumericProperty(0)
    found_count = NumericProperty(0)
    notes = ListProperty([])
    test_code = StringProperty("")
    suggested_alias = StringProperty("")
    saved = ListProperty([])
    diagnosis_status = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.wizard = None
        self._firma_lista = None
        self._teclado = False

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
            post=kivy_post,
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

    def on_enter(self, *args):
        self._escuchar_teclado(True)
        Clock.schedule_once(lambda _dt: self._enfocar_principal(), 0)

    def on_leave(self, *args):
        self._escuchar_teclado(False)

    # -- dibujo ---------------------------------------------------------------

    def _sync(self):
        w = self.wizard
        if w is None:
            return
        paso_anterior = self.step
        self.step = w.step
        self.message = w.message
        self.guide = w.guide
        self.busy = w.busy
        self.searching = w.searching
        self.show_all = w.show_all
        self.hidden_count = w.hidden_count
        self.notes = w.notes
        self.test_code = w.test_code
        self.suggested_alias = w.suggested_alias
        self.saved = list(w.saved)
        encontradas = w.found
        self.found_count = len(encontradas)
        pasos = self.ids.get("pasos") if hasattr(self, "ids") else None
        if pasos is not None and pasos.has_screen(w.step):
            pasos.current = w.step
        self._dibujar_lista(encontradas)
        if w.step != paso_anterior:
            Clock.schedule_once(lambda _dt: self._enfocar_principal(), 0)

    def _dibujar_lista(self, encontradas):
        lista = self.ids.get("lista") if hasattr(self, "ids") else None
        if lista is None:
            return
        firma = (tuple((f.key, f.configured_as, f.hidden) for f in encontradas), self.show_details)
        if firma == self._firma_lista:
            return
        self._firma_lista = firma
        lista.clear_widgets()
        for f in encontradas:
            lista.add_widget(ImpresoraItem(
                clave=f.key,
                titulo=f.title,
                subtitulo=f.subtitle,
                nota=f.note,
                detalles="\n".join(f.details),
                configurada=f.configured_as,
                oculta_por=f.hidden_reason if f.hidden else "",
                seleccionable=f.selectable or bool(f.guide),
                mostrar_detalles=self.show_details,
                pantalla=self,
            ))

    def _enfocar_principal(self):
        """El foco va a la acción principal del paso (Enter la toca).
        En "confirmar" no: un Enter por costumbre no puede decir que salió."""
        clave = FOCO_INICIAL.get(self.step)
        if clave is None:
            return
        objetivo = self.ids.get(clave) if hasattr(self, "ids") else None
        if objetivo is not None and not objetivo.disabled:
            objetivo.focus = True

    # -- teclado ----------------------------------------------------------------

    def _escuchar_teclado(self, activo):
        try:
            from kivy.core.window import Window
        except Exception:
            return
        if activo and not self._teclado:
            Window.bind(on_keyboard=self._on_keyboard)
            self._teclado = True
        elif not activo and self._teclado:
            Window.unbind(on_keyboard=self._on_keyboard)
            self._teclado = False

    def _on_keyboard(self, _window, key, *_args):
        if key != TECLA_ESCAPE:
            return False
        # Escape vuelve atrás; nunca cierra la app (Kivy lo haría por defecto).
        if self.step not in (STEP_INTRO, "guardada", "probando"):
            self.back()
        return True

    def _exit(self, motivo):
        app = App.get_running_app()
        if app is not None and hasattr(app, "leave_printer_setup"):
            app.leave_printer_setup(motivo)

    # -- acciones de la interfaz (delegan en el asistente) ----------------------

    def search(self):
        self.ensure_wizard().search()

    def cancel_search(self):
        self.ensure_wizard().cancel_search()

    def choose_found(self, clave):
        self.ensure_wizard().choose_found(clave)

    def toggle_show_all(self):
        self.ensure_wizard().toggle_show_all()

    def toggle_details(self):
        self.show_details = not self.show_details
        self._firma_lista = None
        self._sync()

    def open_guide(self):
        from fiscalberry.common.printer_guides import open_guide
        if self.guide and not open_guide(self.guide):
            logger.warning(f"No se pudo abrir la guía '{self.guide}'")

    def copy_diagnosis(self):
        """"Copiar diagnóstico" (#185): al portapapeles y a un archivo junto al registro."""
        from fiscalberry.common import support_report

        texto = armar_diagnostico(self.ensure_wizard())
        ruta = support_report.save_report(texto)
        try:
            copiar_al_portapapeles(texto)
            self.diagnosis_status = "Copiado: pegalo en el chat de soporte."
        except Exception as e:
            logger.warning(f"No se pudo copiar el diagnóstico: {e}")
            self.diagnosis_status = ("No se pudo copiar. Quedó guardado en la carpeta del registro."
                                     if ruta else "No se pudo copiar el diagnóstico.")
        Clock.schedule_once(lambda _dt: setattr(self, "diagnosis_status", ""), 8)

    def view_log(self):
        """"Ver registro": la pantalla de logs, que vuelve al asistente."""
        if self.manager is None or not self.manager.has_screen("logs"):
            return
        self.manager.get_screen("logs").volver_a = self.name
        self.manager.current = "logs"

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
