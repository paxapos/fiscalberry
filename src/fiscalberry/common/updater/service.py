"""
El hilo que decide cuándo y qué actualizar.

Regla central: **tener instalado exactamente lo que dice el último release**,
no "actualizar si hay algo más nuevo". La diferencia importa: si un release sale
malo y se borra, GitHub vuelve a apuntar al anterior y la flota baja sola. Con
la regla "solo hacia adelante", un release malo sería irreversible a distancia.

Regla de seguridad: esto es un servidor de impresión. Actualizar con un ticket
en la cola es perder el ticket, así que nunca se aplica nada si el spooler tiene
trabajo pendiente.
"""

import os
import threading
import time

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.updater import (
    appliers,
    commit_guard,
    install_kind,
    release_source,
    selftest,
    staging,
)
from fiscalberry.version import VERSION

logger = getLogger("Updater")

# Primer chequeo al arrancar: se espera un rato para no competir con la conexión
# inicial ni con la ráfaga de impresiones de la apertura del local.
FIRST_CHECK_DELAY_SECONDS = 300
DEFAULT_INTERVAL_HOURS = 6
# Si la cola de impresión está ocupada, se reintenta pronto en vez de esperar
# el intervalo completo.
BUSY_RETRY_SECONDS = 600

TARBALL_URL = "https://github.com/{repo}/archive/refs/tags/{tag}.tar.gz"


def spooler_idle():
    """
    True si NO hay trabajo de impresión pendiente.

    Se mira el spooler solo si ya existe: preguntarle a `get_print_spooler()`
    lo crearía (y arrancaría su hilo) en un proceso que quizá nunca imprime.
    """
    try:
        from fiscalberry.common import ComandosHandler
        spooler = getattr(ComandosHandler, "_print_spooler", None)
        if spooler is None:
            return True
        return spooler.pending_count() == 0
    except Exception as e:
        logger.debug(f"No se pudo consultar la cola de impresión: {e}")
        # Ante la duda, NO actualizar.
        return False


class UpdaterService:
    def __init__(self, config=None, shutdown_cb=None, repo=None):
        self._config = config
        self._shutdown_cb = shutdown_cb
        self._repo = repo or release_source.DEFAULT_REPO
        self._stop = threading.Event()
        self._thread = None
        self.last_result = None

    # -- configuración ----------------------------------------------------

    def _cfg(self, clave, defecto):
        if self._config is None:
            return defecto
        try:
            valor = self._config.get("Updater", clave, fallback=defecto)
            return valor if valor not in ("", None) else defecto
        except Exception:
            return defecto

    def enabled(self):
        valor = str(self._cfg("enabled", "true")).strip().lower()
        return valor not in ("false", "0", "no", "off")

    def interval_seconds(self):
        try:
            horas = float(self._cfg("check_interval_hours", DEFAULT_INTERVAL_HOURS))
        except (TypeError, ValueError):
            horas = DEFAULT_INTERVAL_HOURS
        return max(600.0, horas * 3600.0)

    # -- ciclo de vida ----------------------------------------------------

    def start(self):
        if not self.enabled():
            logger.info("Auto-actualización desactivada por configuración.")
            return None
        if self._thread and self._thread.is_alive():
            return self._thread
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="fiscalberry-updater")
        self._thread.start()
        return self._thread

    def stop(self):
        self._stop.set()

    def _loop(self):
        # Espera inicial interrumpible.
        if self._stop.wait(FIRST_CHECK_DELAY_SECONDS):
            return
        while not self._stop.is_set():
            try:
                resultado = self.check_once()
            except Exception as e:
                logger.error("Error inesperado en el chequeo de actualización: %s", e)
                resultado = ("error", str(e))
            self.last_result = resultado

            espera = (BUSY_RETRY_SECONDS if resultado and resultado[0] == "ocupado"
                      else self.interval_seconds())
            if self._stop.wait(espera):
                return

    # -- el chequeo -------------------------------------------------------

    def check_once(self):
        """
        Un ciclo completo. Devuelve (estado, detalle) para logs y tests.

        Estados: al-dia, sin-artefacto, sin-checksums, ocupado, descartado,
                 aplicado, error.
        """
        kind = install_kind.detect()

        # Restos de ciclos anteriores. Importa sobre todo en Android: el APK no
        # se puede borrar al terminar el ciclo (lo lee el instalador del sistema
        # después), así que si el usuario posterga la instalación queda ocupando
        # ~44 MB, y el chequeo siguiente baja otro.
        try:
            staging.cleanup_stale()
        except Exception as e:
            logger.debug(f"No se pudo limpiar el staging viejo: {e}")

        try:
            release = release_source.fetch_latest(self._repo)
        except release_source.ReleaseUnavailable as e:
            logger.info("No se pudo consultar el release vigente (%s). "
                        "Se reintenta más tarde.", e)
            return ("error", str(e))

        if not release.version:
            return ("error", "el release no tiene tag")

        if release.version == VERSION:
            logger.debug("Ya corriendo la versión vigente (%s).", VERSION)
            return ("al-dia", VERSION)

        direccion = release_source.compare(release.version, VERSION)
        verbo = "Actualizando" if direccion > 0 else "Volviendo atrás"
        logger.info("%s: instalada %s, vigente %s.", verbo, VERSION, release.version)

        if kind == install_kind.SOURCE:
            return self._aplicar_source(release)

        nombre_asset = install_kind.asset_name(kind)
        asset = release.asset(nombre_asset) if nombre_asset else None
        if not asset:
            # Pasa de verdad: el build de Android es best-effort y la CI publica
            # el release igual si falla. No es un error, es "no hay nada para mí".
            logger.info("El release %s no trae %s: nada que hacer en esta "
                        "plataforma.", release.tag, nombre_asset)
            return ("sin-artefacto", nombre_asset)

        sums = release_source.fetch_checksums(release)
        esperado = sums.get(nombre_asset)
        if not esperado:
            logger.warning("Sin checksum publicado para %s: no se actualiza "
                           "(preferimos quedarnos como estamos antes que "
                           "instalar algo sin verificar).", nombre_asset)
            return ("sin-checksums", nombre_asset)

        dir_staging = staging.new_staging()
        try:
            descarga = os.path.join(dir_staging, nombre_asset)
            staging.download(asset["url"], descarga, esperado,
                             expected_size=asset.get("size"))

            if kind == install_kind.ANDROID:
                return self._aplicar_android(descarga, release, dir_staging)

            return self._aplicar_binario(kind, descarga, release, dir_staging)
        except staging.StagingError as e:
            logger.error("Actualización descartada: %s", e)
            staging.cleanup(dir_staging)
            return ("descartado", str(e))
        except appliers.ApplyError as e:
            logger.error("No se pudo aplicar la actualización: %s", e)
            staging.cleanup(dir_staging)
            return ("error", str(e))

    def _aplicar_binario(self, kind, descarga, release, dir_staging):
        # Onedir: se reemplaza la CARPETA de instalación, no un archivo suelto.
        # El ejecutable necesita su `_internal` de la misma versión al lado.
        destino = install_kind.current_app_dir(kind)
        if not destino:
            staging.cleanup(dir_staging)
            return ("error", "no se pudo determinar la instalación a reemplazar")

        nombre_binario = install_kind.binary_name(kind)
        extraido = staging.extract(descarga, os.path.join(dir_staging, "x"))
        nuevo_dir = staging.find_app_dir(
            extraido, install_kind.app_dir_name(kind), nombre_binario)
        binario = os.path.join(nuevo_dir, nombre_binario)

        # LA prueba que importa: que el binario nuevo arranque de verdad.
        ok, detalle = selftest.run(binario, expected_version=release.version)
        if not ok:
            logger.error("El binario %s NO pasó el selftest: %s. "
                         "Se descarta y seguimos en %s.",
                         release.version, detalle, VERSION)
            staging.cleanup(dir_staging)
            return ("descartado", detalle)
        logger.info("El binario %s pasó el selftest.", release.version)

        if not spooler_idle():
            logger.info("Hay impresiones pendientes: se pospone la actualización.")
            staging.cleanup(dir_staging)
            return ("ocupado", "cola de impresión no vacía")

        appliers.apply_for_kind(kind, nuevo_dir=nuevo_dir, destino_dir=destino,
                                binario=nombre_binario,
                                version=release.version, version_previa=VERSION)
        staging.cleanup(dir_staging)
        self._pedir_reinicio()
        return ("aplicado", release.version)

    def _aplicar_android(self, apk, release, dir_staging):
        if not spooler_idle():
            logger.info("Hay impresiones pendientes: se pospone la actualización.")
            staging.cleanup(dir_staging)
            return ("ocupado", "cola de impresión no vacía")
        # El APK NO se limpia: el instalador del sistema lo necesita después de
        # que esta función retorne.
        appliers.apply_android(apk, release.version, VERSION)
        return ("aplicado", release.version)

    def _aplicar_source(self, release):
        if not spooler_idle():
            return ("ocupado", "cola de impresión no vacía")
        url = TARBALL_URL.format(repo=self._repo, tag=release.tag)
        appliers.apply_source(url, release.version, VERSION)
        self._pedir_reinicio()
        return ("aplicado", release.version)

    def _pedir_reinicio(self):
        """
        Termina este proceso para que arranque el binario nuevo.

        Quién lo vuelve a levantar depende del entorno: systemd en Raspberry y
        Linux, y el propio applier (que ya dejó lanzado el reemplazo) en los
        demás casos.
        """
        logger.info("Cerrando para que tome efecto la versión nueva.")
        if self._shutdown_cb:
            try:
                self._shutdown_cb()
                return
            except Exception as e:
                logger.error("El cierre ordenado falló (%s); se sale igual.", e)
        os._exit(0)


# --------------------------------------------------------------------------
# Arranque: reversión y confirmación
# --------------------------------------------------------------------------

def on_process_start():
    """
    Se llama apenas arranca el proceso, antes de levantar nada.

    Si venimos de una actualización que no llegó a confirmarse varias veces
    seguidas, revierte al binario anterior.
    """
    try:
        pendiente, revertir = commit_guard.register_boot()
    except Exception as e:
        logger.warning(f"No se pudo evaluar la marca de actualización: {e}")
        return False

    if pendiente and revertir:
        if appliers.rollback(pendiente):
            logger.warning("Se revirtió a %s. Reiniciando.",
                           pendiente.previous_version)
            os._exit(0)
    return bool(pendiente)


def on_services_ready():
    """
    Se llama cuando los servicios ya levantaron. Confirma la actualización.

    Es el punto exacto donde se distingue "el binario ejecuta" de "el servicio
    funciona": el selftest ya probó lo primero; esto prueba lo segundo.
    """
    try:
        return commit_guard.confirm()
    except Exception as e:
        logger.warning(f"No se pudo confirmar la actualización: {e}")
        return False
