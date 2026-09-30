# coding=utf-8
"""
Navegación del asistente de impresoras (#173).

Criterios de aceptación que se fijan acá:

- Un equipo recién vinculado ve el asistente y el servicio (MQTT) queda activo.
- "Configurar después" lleva a la pantalla principal y el asistente se puede
  volver a abrir.
- Una instalación existente arranca como hasta ahora.
- Linux y Android no cambian (regresión multiplataforma).
- El estado se deriva de las impresoras configuradas, no solo de una marca.
"""

import sys
import types

import pytest

from fiscalberry.common import onboarding
from fiscalberry.common.onboarding import OnboardingStore, should_show_wizard, wizard_supported


class ConfigFalso:
    def __init__(self, adoptado=True, impresoras=None):
        self.adoptado = adoptado
        self.data = {"SERVIDOR": {"uuid": "x"}}
        self.data.update(impresoras or {})

    def is_comercio_adoptado(self):
        return self.adoptado

    def get_actual_config(self):
        return {s: dict(v) for s, v in self.data.items()}


@pytest.fixture
def store(tmp_path, monkeypatch):
    ruta = tmp_path / "onboarding.json"
    monkeypatch.setattr(onboarding, "_default_path", lambda: str(ruta))
    monkeypatch.delenv(onboarding.ENV_FORCE, raising=False)
    monkeypatch.delenv("ANDROID_ARGUMENT", raising=False)
    monkeypatch.delenv("ANDROID_APP_PATH", raising=False)
    return OnboardingStore()


COCINA = {"Cocina": {"driver": "Network", "host": "192.168.1.80"}}


# ---------------------------------------------------------------------------
# Dónde existe el asistente
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform,entorno,esperado", [
    ("win32", {}, True),
    ("linux", {}, False),
    ("darwin", {}, False),
    ("linux", {"ANDROID_ARGUMENT": "/data/app"}, False),
    ("win32", {"ANDROID_APP_PATH": "/x"}, False),
    ("linux", {onboarding.ENV_FORCE: "1"}, True),   # para desarrollo
])
def test_el_asistente_solo_existe_en_windows(platform, entorno, esperado):
    assert wizard_supported(platform=platform, environ=entorno) is esperado


# ---------------------------------------------------------------------------
# Cuándo se muestra solo
# ---------------------------------------------------------------------------

def test_recien_vinculado_sin_impresoras_se_muestra(store):
    store.mark_pending()
    assert should_show_wizard(ConfigFalso(), store, platform="win32", environ={}) is True


def test_omitido_no_vuelve_a_aparecer_solo(store):
    store.mark_pending()
    store.mark_skipped()
    assert should_show_wizard(ConfigFalso(), store, platform="win32", environ={}) is False


def test_con_impresoras_configuradas_no_se_muestra_aunque_la_marca_diga_pendiente(store):
    """El estado se deriva de la configuración, no solo de la marca."""
    store.mark_pending()
    assert should_show_wizard(ConfigFalso(impresoras=COCINA), store,
                              platform="win32", environ={}) is False


def test_una_instalacion_existente_sin_marca_arranca_como_siempre(store):
    """Muchas imprimen con impresoras que manda el backend: no se las fuerza."""
    assert should_show_wizard(ConfigFalso(), store, platform="win32", environ={}) is False


def test_sin_vincular_no_se_muestra(store):
    store.mark_pending()
    assert should_show_wizard(ConfigFalso(adoptado=False), store,
                              platform="win32", environ={}) is False


@pytest.mark.parametrize("platform,entorno", [
    ("linux", {}),
    ("linux", {"ANDROID_ARGUMENT": "/data/app"}),
])
def test_linux_y_android_no_cambian(store, platform, entorno):
    store.mark_pending()
    assert should_show_wizard(ConfigFalso(), store, platform=platform, environ=entorno) is False


def test_la_marca_sobrevive_entre_arranques_y_tolera_basura(store):
    store.mark_pending()
    assert OnboardingStore(store.path).pending is True

    with open(store.path, "w") as fh:
        fh.write("{no es json")
    assert OnboardingStore(store.path).pending is False


# ---------------------------------------------------------------------------
# La App: después de vincular, el asistente o la pantalla principal
# ---------------------------------------------------------------------------

class PantallaAsistenteFalsa:
    def __init__(self):
        self.abierta = 0

    def open_fresh(self):
        self.abierta += 1


class ScreenManagerFalso:
    def __init__(self, actual="adopt", con_asistente=True):
        self.current = actual
        self.asistente = PantallaAsistenteFalsa()
        self._pantallas = {"adopt", "main", "logs"} | ({"printer_setup"} if con_asistente else set())

    def has_screen(self, nombre):
        return nombre in self._pantallas

    def get_screen(self, nombre):
        assert nombre == "printer_setup"
        return self.asistente


@pytest.fixture
def app_cls():
    from fiscalberry.ui.fiscalberry_app import FiscalberryApp
    return FiscalberryApp


class AppFalsa:
    """Lo mínimo de FiscalberryApp para correr sus métodos sin levantar Kivy."""

    def __init__(self, app_cls, config, con_asistente=True, android=False, actual="adopt"):
        self._cls = app_cls
        self._configberry = config
        self.printer_wizard_available = con_asistente
        self._is_android = android
        self.root = ScreenManagerFalso(actual, con_asistente)
        self.servicios = 0
        self.servicio_android = 0
        self.tenant = "pizzeria"

    def updatePropertiesWithConfig(self):
        pass

    def on_start_service(self):
        self.servicios += 1

    def on_stop_service(self):
        self.servicios = 0

    def _start_android_service(self):
        self.servicio_android += 1

    def _pantalla_tras_adopcion(self):
        return self._cls._pantalla_tras_adopcion(self)

    def after_adoption(self):
        return self._cls.after_adoption(self)


@pytest.fixture
def en_windows(monkeypatch):
    monkeypatch.setattr(onboarding.sys, "platform", "win32")


def test_recien_vinculado_ve_el_asistente_y_el_servicio_queda_activo(app_cls, store, en_windows):
    app = AppFalsa(app_cls, ConfigFalso())

    app.after_adoption()

    assert app.root.current == "printer_setup"
    assert app.root.asistente.abierta == 1
    assert app.servicios == 1            # MQTT arriba aunque esté en el asistente
    assert store.pending is True         # si reinicia la PC, sigue pendiente


def test_vincular_dos_veces_no_duplica_nada(app_cls, store, en_windows):
    """La pantalla de vinculación y el cambio de config disparan lo mismo."""
    app = AppFalsa(app_cls, ConfigFalso())

    app.after_adoption()
    app.after_adoption()

    assert app.servicios == 1
    assert app.root.asistente.abierta == 1


def test_en_linux_despues_de_vincular_va_a_la_principal(app_cls, store, monkeypatch):
    monkeypatch.setattr(onboarding.sys, "platform", "linux")
    app = AppFalsa(app_cls, ConfigFalso(), con_asistente=False)

    app.after_adoption()

    assert app.root.current == "main"
    assert app.servicios == 1
    assert store.read() == {}  # ni siquiera se deja la marca


def test_en_android_se_arranca_tambien_el_servicio_foreground(app_cls, store):
    app = AppFalsa(app_cls, ConfigFalso(), con_asistente=False, android=True)

    app.after_adoption()

    assert app.root.current == "main"
    assert app.servicio_android == 1


def test_si_ya_hay_impresoras_despues_de_vincular_va_a_la_principal(app_cls, store, en_windows):
    """Revincular un equipo que ya imprimía no lo manda al asistente."""
    app = AppFalsa(app_cls, ConfigFalso(impresoras=COCINA))

    app.after_adoption()

    assert app.root.current == "main"


def test_una_instalacion_existente_arranca_en_la_principal(app_cls, store, en_windows):
    app = AppFalsa(app_cls, ConfigFalso(), actual="main")
    assert app._pantalla_tras_adopcion() == "main"


def test_si_el_comercio_quedo_pendiente_se_retoma_al_arrancar(app_cls, store, en_windows):
    """Se cerró la app o se reinició la PC en medio del asistente."""
    store.mark_pending()
    app = AppFalsa(app_cls, ConfigFalso(), actual="main")
    assert app._pantalla_tras_adopcion() == "printer_setup"


# ---------------------------------------------------------------------------
# Salir y volver a entrar
# ---------------------------------------------------------------------------

def test_configurar_despues_lleva_a_la_principal_y_se_puede_reabrir(app_cls, store, en_windows):
    from fiscalberry.common.printer_wizard import EXIT_SKIPPED

    app = AppFalsa(app_cls, ConfigFalso())
    app.after_adoption()

    app_cls.leave_printer_setup(app, EXIT_SKIPPED)

    assert app.root.current == "main"
    assert store.skipped is True
    assert app.servicios == 1                     # el servicio sigue
    assert app._pantalla_tras_adopcion() == "main"  # no se impone de nuevo

    app_cls.open_printer_setup(app)               # botón "Impresoras"
    assert app.root.current == "printer_setup"
    assert app.root.asistente.abierta == 2        # empieza de cero


def test_terminar_deja_el_asistente_hecho(app_cls, store, en_windows):
    from fiscalberry.common.printer_wizard import EXIT_FINISHED

    app = AppFalsa(app_cls, ConfigFalso())
    app.after_adoption()
    app_cls.leave_printer_setup(app, EXIT_FINISHED)

    assert app.root.current == "main"
    assert store.read().get("done") is True


def test_sin_vincular_el_boton_impresoras_lleva_a_vincular(app_cls, store, en_windows):
    app = AppFalsa(app_cls, ConfigFalso(adoptado=False), actual="main")
    app_cls.open_printer_setup(app)
    assert app.root.current == "adopt"


def test_sin_asistente_el_boton_no_hace_nada(app_cls, store):
    app = AppFalsa(app_cls, ConfigFalso(), con_asistente=False, actual="main")
    app_cls.open_printer_setup(app)
    assert app.root.current == "main"


# ---------------------------------------------------------------------------
# Cambios de configuración mientras se usa la app
# ---------------------------------------------------------------------------

def _cambio_de_config(app_cls, app):
    # _on_config_change está decorado con @mainthread: se llama la función
    # original para no depender del Clock de Kivy.
    original = app_cls._on_config_change
    funcion = getattr(original, "__wrapped__", original)
    funcion(app, {})


@pytest.mark.parametrize("pantalla", ["printer_setup", "logs", "main"])
def test_guardar_una_impresora_no_saca_a_la_persona_de_donde_esta(app_cls, store, en_windows,
                                                                  pantalla):
    """Antes, cualquier cambio del config.ini mandaba a la pantalla principal."""
    app = AppFalsa(app_cls, ConfigFalso(), actual=pantalla)
    _cambio_de_config(app_cls, app)
    assert app.root.current == pantalla


def test_el_cambio_de_config_de_la_vinculacion_sigue_llevando_adelante(app_cls, store, en_windows):
    app = AppFalsa(app_cls, ConfigFalso(), actual="adopt")
    _cambio_de_config(app_cls, app)
    assert app.root.current == "printer_setup"
    assert app.servicios == 1


def test_desvincular_sigue_volviendo_a_la_vinculacion(app_cls, store, en_windows):
    app = AppFalsa(app_cls, ConfigFalso(), actual="printer_setup")
    app.tenant = ""
    _cambio_de_config(app_cls, app)
    assert app.root.current == "adopt"
