"""
Cuándo mostrar el asistente de impresoras (#173).

Reglas:

- Solo en Windows de escritorio. En Linux y Android nada cambia (se puede
  forzar con FISCALBERRY_PRINTER_WIZARD=1 para desarrollo).
- Se muestra solo en instalaciones NUEVAS: la marca "pendiente" se deja al
  vincular el comercio. Una instalación que ya existía (sin marca) arranca
  como siempre, tenga o no impresoras en el config.ini: muchas imprimen con
  impresoras que manda el backend en cada ticket.
- El estado se deriva de la configuración, no solo de la marca: si ya hay una
  impresora válida (del asistente, del backend o de soporte), no se muestra.
- "Configurar después" deja la marca como omitida: no vuelve a aparecer solo,
  pero se puede abrir desde la pantalla principal o la bandeja.

La marca vive en un JSON aparte del config.ini: una sección más ahí la
verían el backend y el discover como si fuera una impresora.
"""

import json
import os
import sys
import time

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("Onboarding")

STATE_FILE = "onboarding.json"
ENV_FORCE = "FISCALBERRY_PRINTER_WIZARD"


def wizard_supported(platform=None, environ=None):
    """El asistente existe en Windows de escritorio (o si se lo fuerza)."""
    environ = os.environ if environ is None else environ
    if environ.get("ANDROID_ARGUMENT") or environ.get("ANDROID_APP_PATH"):
        return False
    if str(environ.get(ENV_FORCE, "")).strip().lower() in ("1", "true", "yes", "on"):
        return True
    return (sys.platform if platform is None else platform) == "win32"


def _default_path():
    import platformdirs
    carpeta = platformdirs.user_data_dir("fiscalberry")
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, STATE_FILE)


class OnboardingStore:
    """La marca del asistente, en disco (sobrevive a reinicios de la PC)."""

    def __init__(self, path=None):
        self._path = path

    @property
    def path(self):
        if self._path is None:
            self._path = _default_path()
        return self._path

    def read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                datos = json.load(fh)
            return datos if isinstance(datos, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.warning(f"Marca del asistente ilegible, se ignora: {e}")
            return {}

    def _write(self, datos):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(datos, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except Exception as e:
            logger.warning(f"No se pudo guardar la marca del asistente: {e}")

    @property
    def pending(self):
        return bool(self.read().get("pending"))

    @property
    def skipped(self):
        return bool(self.read().get("skipped"))

    def mark_pending(self):
        """El comercio se acaba de vincular en este equipo."""
        self._write({"pending": True, "skipped": False, "since": time.time()})

    def mark_skipped(self):
        """"Configurar después": no vuelve a aparecer solo."""
        self._write({"pending": False, "skipped": True, "at": time.time()})

    def mark_done(self):
        self._write({"pending": False, "skipped": False, "done": True, "at": time.time()})


def has_configured_printers(config):
    from fiscalberry.common.printer_setup import PrinterSetupService

    try:
        return PrinterSetupService(config).has_configured_printers()
    except Exception as e:
        logger.warning(f"No se pudo leer la configuración de impresoras: {e}")
        # Ante la duda, como si hubiera: no se fuerza el asistente.
        return True


def should_show_wizard(config, store=None, platform=None, environ=None):
    """¿Hay que llevar a la persona al asistente en vez de a la pantalla principal?"""
    if not wizard_supported(platform, environ):
        return False
    try:
        if not config.is_comercio_adoptado():
            return False
    except Exception:
        return False
    if has_configured_printers(config):
        return False
    return (store or OnboardingStore()).pending
