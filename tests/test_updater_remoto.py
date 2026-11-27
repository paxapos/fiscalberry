# coding=utf-8
"""
Comando remoto `upgrade` (S10): "buscá la última y aplicala ya".

Lo que se protege:
- el pedido remoto corre el mismo chequeo que el periódico (contra `latest`)
  y aplica si hay versión nueva;
- el chequeo remoto no corre a la vez que el periódico;
- el pedido por MQTT no se bloquea durante la descarga;
- `upgrade`, `reboot` y `restart` por `send_command` no revientan.
"""

import threading

import pytest

from fiscalberry.common.updater import (
    install_kind,
    release_source,
    service,
    staging,
)
from fiscalberry.version import VERSION

ASSET_CLI = "fiscalberry-linux-cli.tar.gz"


class FakeConfig:
    """Lo mínimo de Configberry que usa el updater: get()."""

    def __init__(self, **updater):
        self.valores = dict(updater)

    def get(self, section, key, fallback=None):
        if section != "Updater":
            return fallback
        return self.valores.get(key, fallback)


class Registro:
    def __init__(self):
        self.aplicado = None
        self.reinicios = 0
        self.consultas = 0


@pytest.fixture(autouse=True)
def hilos_remotos_terminan():
    """Un test no puede dejar un chequeo remoto vivo para el siguiente."""
    yield
    _esperar_remoto()
    assert not service._CHECK_LOCK.locked()


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Instalación Linux-CLI, cola vacía, todo listo para aplicar; sin red."""
    reg = Registro()

    from fiscalberry.common.updater import commit_guard
    monkeypatch.setattr(commit_guard, "_state_path",
                        lambda: str(tmp_path / "update_pending.json"))

    destino = tmp_path / "inst" / "fiscalberry-cli"
    destino.mkdir(parents=True)
    nuevo = tmp_path / "nuevo" / "fiscalberry-cli"
    nuevo.mkdir(parents=True)
    (nuevo / "fiscalberry-cli").write_bytes(b"binario nuevo")

    monkeypatch.setattr(install_kind, "detect", lambda: install_kind.LINUX_CLI)
    monkeypatch.setattr(install_kind, "current_app_dir", lambda kind: str(destino))
    monkeypatch.setattr(service, "spooler_idle", lambda: True)
    monkeypatch.setattr(service, "_active", None)

    (tmp_path / "st").mkdir()
    monkeypatch.setattr(staging, "new_staging", lambda **kw: str(tmp_path / "st"))
    monkeypatch.setattr(staging, "cleanup", lambda p: None)
    monkeypatch.setattr(staging, "cleanup_stale", lambda: None)
    monkeypatch.setattr(staging, "download", lambda url, dest, sha, **kw: dest)
    monkeypatch.setattr(staging, "extract", lambda a, d: d)
    monkeypatch.setattr(staging, "find_app_dir",
                        lambda raiz, nombre_dir, nombre_bin: str(nuevo))
    monkeypatch.setattr(service.selftest, "run",
                        lambda binario, expected_version=None: (True, "ok"))

    def fake_apply(kind, **kwargs):
        reg.aplicado = kwargs
        return True

    monkeypatch.setattr(service.appliers, "apply_for_kind", fake_apply)
    monkeypatch.setattr(service.UpdaterService, "_pedir_reinicio",
                        lambda self: setattr(reg, "reinicios", reg.reinicios + 1))

    def fake_latest(repo=None, session=None):
        reg.consultas += 1
        return release_source.Release(
            tag="v99.0.0", version="99.0.0",
            assets={ASSET_CLI: {"url": f"https://x/{ASSET_CLI}", "size": 10}})

    monkeypatch.setattr(release_source, "fetch_latest", fake_latest)
    monkeypatch.setattr(release_source, "fetch_checksums",
                        lambda release, session=None: {ASSET_CLI: "0" * 64})
    return reg


def _esperar_remoto():
    for h in threading.enumerate():
        if h.name == "fiscalberry-updater-remoto":
            h.join(timeout=5)


# -- pedido remoto -------------------------------------------------------

def test_request_check_corre_un_chequeo_y_aplica_si_hay_version_nueva(entorno):
    svc = service.UpdaterService(config=FakeConfig())

    r = svc.request_check()
    _esperar_remoto()

    assert r == {"accepted": True, "current": VERSION}
    assert entorno.consultas == 1
    assert entorno.aplicado["version"] == "99.0.0"
    assert entorno.reinicios == 1
    assert svc.last_result == ("aplicado", "99.0.0")


def test_request_check_al_dia_no_aplica(entorno, monkeypatch):
    monkeypatch.setattr(release_source, "fetch_latest",
                        lambda repo=None, session=None: release_source.Release(
                            tag=f"v{VERSION}", version=VERSION, assets={}))
    svc = service.UpdaterService(config=FakeConfig())

    svc.request_check()
    _esperar_remoto()

    assert svc.last_result == ("al-dia", VERSION)
    assert entorno.aplicado is None


def test_request_check_respeta_la_cola_de_impresion(entorno, monkeypatch):
    monkeypatch.setattr(service, "spooler_idle", lambda: False)
    svc = service.UpdaterService(config=FakeConfig())

    svc.request_check()
    _esperar_remoto()

    assert svc.last_result[0] == "ocupado"
    assert entorno.aplicado is None


def test_dos_chequeos_no_corren_a_la_vez(entorno, monkeypatch):
    adentro = threading.Event()
    soltar = threading.Event()

    def lento(self):
        adentro.set()
        soltar.wait(5)
        return ("al-dia", VERSION)

    monkeypatch.setattr(service.UpdaterService, "_check_once_sin_lock", lento)
    svc = service.UpdaterService(config=FakeConfig())

    primero = svc.request_check()
    assert primero["accepted"] is True
    assert adentro.wait(5)

    segundo = svc.request_check()
    periodico = svc.check_once()
    soltar.set()
    _esperar_remoto()

    assert segundo == {"accepted": False, "current": VERSION,
                       "reason": "ya hay un chequeo en curso"}
    assert periodico[0] == "ocupado"


def test_request_check_no_bloquea_al_que_llama(entorno, monkeypatch):
    soltar = threading.Event()
    monkeypatch.setattr(service.UpdaterService, "_check_once_sin_lock",
                        lambda self: (soltar.wait(5), ("al-dia", VERSION))[1])
    svc = service.UpdaterService(config=FakeConfig())

    r = svc.request_check()

    assert r["accepted"] is True
    assert svc.last_result is None
    soltar.set()
    _esperar_remoto()
    assert svc.last_result == ("al-dia", VERSION)


def test_error_inesperado_en_el_chequeo_remoto_suelta_el_lock(entorno, monkeypatch):
    def revienta(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(service.UpdaterService, "_check_once_sin_lock", revienta)
    svc = service.UpdaterService(config=FakeConfig())

    svc.request_check()
    _esperar_remoto()

    assert svc.last_result == ("error", "boom")


# -- servicio activo / armado al vuelo ----------------------------------

def test_request_remote_update_usa_el_servicio_activo(entorno, monkeypatch):
    activo = service.UpdaterService(config=FakeConfig())
    monkeypatch.setattr(service, "_active", activo)

    r = service.request_remote_update(config=FakeConfig())
    _esperar_remoto()

    assert r["accepted"] is True
    assert activo.last_result == ("aplicado", "99.0.0")


def test_start_registra_el_servicio_activo_y_stop_lo_saca(entorno, monkeypatch):
    monkeypatch.setattr(service, "FIRST_CHECK_DELAY_SECONDS", 60)
    svc = service.UpdaterService(config=FakeConfig(enabled="true"))

    svc.start()
    try:
        assert service._active is svc
    finally:
        svc.stop()
    assert service._active is None


def test_request_remote_update_arma_uno_al_vuelo_si_esta_desactivado(entorno):
    cfg = FakeConfig(enabled="false")

    r = service.request_remote_update(config=cfg)
    _esperar_remoto()

    assert r["accepted"] is True
    assert entorno.aplicado["version"] == "99.0.0"


# -- los comandos por ComandosHandler -----------------------------------

def test_upgrade_true_por_send_command_no_devuelve_error(entorno, monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import fiscalberry.common.ComandosHandler as CH

    activo = service.UpdaterService(config=FakeConfig())
    monkeypatch.setattr(service, "_active", activo)

    resp = CH.ComandosHandler().send_command({"upgrade": True})
    _esperar_remoto()

    assert "err" not in resp
    assert resp["rta"]["rta"] == {"accepted": True, "current": VERSION}
    assert entorno.consultas == 1
    assert activo.last_result == ("aplicado", "99.0.0")


def test_restart_sin_supervisor_devuelve_error_explicito(monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import fiscalberry.common.ComandosHandler as CH

    # reboot/restart remotos vienen apagados por defecto: se habilitan en el config local.
    monkeypatch.setattr(CH, "_remote_power_commands_enabled", lambda: True)

    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.setattr(CH.ComandosHandler, "_app_gui_en_ejecucion",
                        staticmethod(lambda: None))

    resp = CH.ComandosHandler().send_command({"restart": True})

    assert "no hay quién vuelva a levantar" in resp["err"]


def test_restart_bajo_systemd_cierra_ordenado_con_demora(monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import fiscalberry.common.ComandosHandler as CH

    # reboot/restart remotos vienen apagados por defecto: se habilitan en el config local.
    monkeypatch.setattr(CH, "_remote_power_commands_enabled", lambda: True)

    monkeypatch.setenv("INVOCATION_ID", "abc")
    monkeypatch.setattr(CH.ComandosHandler, "_app_gui_en_ejecucion",
                        staticmethod(lambda: None))
    timers = []

    class FakeTimer:
        def __init__(self, segundos, fn):
            self.segundos, self.fn, self.daemon = segundos, fn, False
            timers.append(self)

        def start(self):
            self.iniciado = True

    monkeypatch.setattr(CH.threading, "Timer", FakeTimer)

    resp = CH.ComandosHandler().send_command({"restart": True})

    assert "err" not in resp
    assert len(timers) == 1 and timers[0].iniciado
    assert timers[0].fn.__name__ == "_cerrar_para_reinicio"


def test_reboot_llama_a_rebootFiscalberry(monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import subprocess
    import fiscalberry.common.ComandosHandler as CH

    # reboot/restart remotos vienen apagados por defecto: se habilitan en el config local.
    monkeypatch.setattr(CH, "_remote_power_commands_enabled", lambda: True)

    llamadas = []
    monkeypatch.setattr(subprocess, "call", lambda cmd: llamadas.append(cmd) or 0)

    resp = CH.ComandosHandler().send_command({"reboot": True})

    assert "err" not in resp
    assert llamadas == [["reboot"]]
    assert resp["rta"]["rta"] == 0


def test_reboot_sin_binario_devuelve_error_explicito(monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import subprocess
    import fiscalberry.common.ComandosHandler as CH

    # reboot/restart remotos vienen apagados por defecto: se habilitan en el config local.
    monkeypatch.setattr(CH, "_remote_power_commands_enabled", lambda: True)

    def no_existe(cmd):
        raise FileNotFoundError("reboot")

    monkeypatch.setattr(subprocess, "call", no_existe)

    resp = CH.ComandosHandler().send_command({"reboot": True})

    assert "no se pudo reiniciar la máquina" in resp["err"]
