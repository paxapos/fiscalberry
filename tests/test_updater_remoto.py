# coding=utf-8
"""
Comando remoto `upgrade` (S10): fijar una versión y "actualizá ahora".

Lo que se protege:
- sin pin se sigue `latest`; con pin se consulta ese tag y el pin sobrevive a
  los chequeos periódicos;
- una versión con basura no llega nunca a una URL de GitHub;
- el chequeo remoto no corre a la vez que el periódico;
- el pedido por MQTT no se bloquea durante la descarga.
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
    """Lo mínimo de Configberry que usa el updater: get() y set()."""

    def __init__(self, **updater):
        self.valores = dict(updater)
        self.sets = []

    def get(self, section, key, fallback=None):
        if section != "Updater":
            return fallback
        return self.valores.get(key, fallback)

    def set(self, section, kwargs):
        self.sets.append((section, dict(kwargs)))
        for k, v in kwargs.items():
            if v is None:
                self.valores.pop(k, None)
            else:
                self.valores[k] = v
        return True


class Registro:
    def __init__(self):
        self.aplicado = None
        self.reinicios = 0
        self.consultas = []


@pytest.fixture(autouse=True)
def hilos_remotos_terminan():
    """Un test no puede dejar un chequeo remoto vivo para el siguiente."""
    yield
    for h in threading.enumerate():
        if h.name == "fiscalberry-updater-remoto":
            h.join(timeout=5)
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

    def _release(version):
        return release_source.Release(
            tag=f"v{version}", version=version,
            assets={ASSET_CLI: {"url": f"https://x/{ASSET_CLI}", "size": 10}})

    def fake_latest(repo=None, session=None):
        reg.consultas.append(("latest", None))
        return _release("99.0.0")

    def fake_tag(version, repo=None, session=None):
        reg.consultas.append(("tag", version))
        return _release(version)

    monkeypatch.setattr(release_source, "fetch_latest", fake_latest)
    monkeypatch.setattr(release_source, "fetch_tag", fake_tag)
    monkeypatch.setattr(release_source, "fetch_checksums",
                        lambda release, session=None: {ASSET_CLI: "0" * 64})

    (tmp_path / "st").mkdir(exist_ok=True)
    return reg


def _esperar_remoto():
    for h in threading.enumerate():
        if h.name == "fiscalberry-updater-remoto":
            h.join(timeout=5)


# -- pin en el chequeo ---------------------------------------------------

def test_sin_pin_sigue_a_latest(entorno):
    estado, detalle = service.UpdaterService(config=FakeConfig()).check_once()

    assert (estado, detalle) == ("aplicado", "99.0.0")
    assert entorno.consultas == [("latest", None)]


def test_con_pin_consulta_el_tag_y_lo_aplica(entorno):
    svc = service.UpdaterService(config=FakeConfig(pinned_version="3.7.1"))

    estado, detalle = svc.check_once()

    assert (estado, detalle) == ("aplicado", "3.7.1")
    assert entorno.consultas == [("tag", "3.7.1")]
    assert entorno.aplicado["version"] == "3.7.1"


def test_el_pin_persiste_en_los_chequeos_periodicos(entorno):
    svc = service.UpdaterService(config=FakeConfig(pinned_version="3.7.1"))

    svc.check_once()
    svc.check_once()

    assert entorno.consultas == [("tag", "3.7.1"), ("tag", "3.7.1")]


def test_pin_ya_instalado_queda_al_dia(entorno):
    svc = service.UpdaterService(config=FakeConfig(pinned_version=VERSION))

    assert svc.check_once() == ("al-dia", VERSION)
    assert entorno.aplicado is None


@pytest.mark.parametrize("basura", ["abc", "3.7.1; rm -rf", "../../x", "3", "1.2.3.4.5"])
def test_pin_invalido_en_config_se_ignora(entorno, basura):
    svc = service.UpdaterService(config=FakeConfig(pinned_version=basura))

    assert svc.pinned_version() is None
    svc.check_once()
    assert entorno.consultas == [("latest", None)]


def test_pin_latest_en_config_es_no_fijar(entorno):
    svc = service.UpdaterService(config=FakeConfig(pinned_version="latest"))

    assert svc.pinned_version() is None


# -- pedido remoto -------------------------------------------------------

def test_request_check_fija_y_aplica(entorno):
    cfg = FakeConfig()
    svc = service.UpdaterService(config=cfg)

    r = svc.request_check("v99.1.0")
    _esperar_remoto()

    assert r == {"accepted": True, "current": VERSION, "target": "99.1.0"}
    assert cfg.valores["pinned_version"] == "99.1.0"
    assert entorno.consultas == [("tag", "99.1.0")]
    assert entorno.aplicado["version"] == "99.1.0"
    assert svc.last_result == ("aplicado", "99.1.0")


def test_request_check_latest_quita_el_pin(entorno):
    cfg = FakeConfig(pinned_version="3.7.1")
    svc = service.UpdaterService(config=cfg)

    r = svc.request_check("latest")
    _esperar_remoto()

    assert r["accepted"] is True
    assert r["target"] == "latest"
    assert "pinned_version" not in cfg.valores
    assert entorno.consultas == [("latest", None)]


def test_request_check_sin_version_respeta_el_pin(entorno):
    cfg = FakeConfig(pinned_version="3.7.1")
    svc = service.UpdaterService(config=cfg)

    r = svc.request_check()
    _esperar_remoto()

    assert r == {"accepted": True, "current": VERSION, "target": "3.7.1"}
    assert cfg.sets == []
    assert entorno.consultas == [("tag", "3.7.1")]


@pytest.mark.parametrize("basura", ["abc", "3.7.1/../x", "", "1.2.3.4.5", "latest2", 3.7, ["3.7.1"]])
def test_version_con_basura_se_rechaza_sin_tocar_nada(entorno, basura):
    cfg = FakeConfig(pinned_version="3.7.1")
    svc = service.UpdaterService(config=cfg)

    with pytest.raises(release_source.InvalidVersion):
        svc.request_check(basura)

    assert cfg.sets == []
    assert cfg.valores["pinned_version"] == "3.7.1"
    assert entorno.consultas == []
    assert not service._CHECK_LOCK.locked()


def test_dos_chequeos_no_corren_a_la_vez(entorno, monkeypatch):
    adentro = threading.Event()
    soltar = threading.Event()

    def lento(self):
        adentro.set()
        soltar.wait(5)
        return ("al-dia", VERSION)

    monkeypatch.setattr(service.UpdaterService, "_check_once_sin_lock", lento)
    cfg = FakeConfig()
    svc = service.UpdaterService(config=cfg)

    primero = svc.request_check("99.1.0")
    assert primero["accepted"] is True
    assert adentro.wait(5)

    segundo = svc.request_check("99.2.0")
    periodico = svc.check_once()
    soltar.set()
    _esperar_remoto()

    assert segundo["accepted"] is False
    assert segundo["reason"] == "ya hay un chequeo en curso"
    assert periodico[0] == "ocupado"
    # El pedido rechazado no pisó el pin del que sí corrió.
    assert cfg.valores["pinned_version"] == "99.1.0"


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


def test_si_no_se_puede_guardar_el_pin_se_rechaza(entorno):
    cfg = FakeConfig()
    cfg.set = lambda section, kwargs: False
    svc = service.UpdaterService(config=cfg)

    r = svc.request_check("99.1.0")

    assert r["accepted"] is False
    assert entorno.consultas == []
    assert not service._CHECK_LOCK.locked()


# -- servicio activo / armado al vuelo ----------------------------------

def test_request_remote_update_usa_el_servicio_activo(entorno, monkeypatch):
    activo = service.UpdaterService(config=FakeConfig())
    monkeypatch.setattr(service, "_active", activo)

    r = service.request_remote_update("99.1.0", config=FakeConfig())
    _esperar_remoto()

    assert r["accepted"] is True
    assert activo.last_result == ("aplicado", "99.1.0")


def test_start_registra_el_servicio_activo_y_stop_lo_saca(entorno, monkeypatch):
    monkeypatch.setattr(service, "FIRST_CHECK_DELAY_SECONDS", 60)
    svc = service.UpdaterService(config=FakeConfig())

    svc.start()
    try:
        assert service._active is svc
    finally:
        svc.stop()
    assert service._active is None


def test_request_remote_update_arma_uno_al_vuelo_si_esta_desactivado(entorno):
    cfg = FakeConfig(enabled="false")

    r = service.request_remote_update("99.1.0", config=cfg)
    _esperar_remoto()

    assert r["accepted"] is True
    assert cfg.valores["pinned_version"] == "99.1.0"
    assert entorno.aplicado["version"] == "99.1.0"


# -- release_source ------------------------------------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("3.7.1", "3.7.1"), ("v3.7.1", "3.7.1"), (" V3.7 ", "3.7"), ("1.2.3.4", "1.2.3.4"),
])
def test_normalize_version_acepta_versiones(entrada, esperado):
    assert release_source.normalize_version(entrada) == esperado


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _Sesion:
    def __init__(self, resp):
        self.resp = resp
        self.urls = []

    def get(self, url, **kw):
        self.urls.append(url)
        return self.resp


def test_fetch_tag_consulta_releases_tags_y_parsea_igual_que_latest():
    sesion = _Sesion(_Resp(200, {
        "tag_name": "v3.7.1",
        "assets": [{"name": ASSET_CLI, "browser_download_url": "https://x/a", "size": 5}],
    }))

    rel = release_source.fetch_tag("3.7.1", "paxapos/fiscalberry", session=sesion)

    assert sesion.urls == [
        "https://api.github.com/repos/paxapos/fiscalberry/releases/tags/v3.7.1"]
    assert rel.version == "3.7.1"
    assert rel.asset(ASSET_CLI)["url"] == "https://x/a"


def test_fetch_tag_404_es_release_inexistente():
    with pytest.raises(release_source.ReleaseUnavailable):
        release_source.fetch_tag("3.7.1", session=_Sesion(_Resp(404)))


def test_fetch_tag_rechaza_versiones_invalidas_sin_pedir_nada():
    sesion = _Sesion(_Resp(200, {}))

    with pytest.raises(release_source.InvalidVersion):
        release_source.fetch_tag("3.7.1/../../x", session=sesion)

    assert sesion.urls == []


# -- el comando por ComandosHandler -------------------------------------

def test_upgrade_true_por_comandos_handler_no_devuelve_error(entorno, monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import fiscalberry.common.ComandosHandler as CH

    activo = service.UpdaterService(config=FakeConfig())
    monkeypatch.setattr(service, "_active", activo)

    resp = CH.ComandosHandler().send_command({"upgrade": True})
    _esperar_remoto()

    assert "err" not in resp
    assert resp["rta"]["rta"]["accepted"] is True
    assert resp["rta"]["rta"]["current"] == VERSION
    assert entorno.consultas == [("latest", None)]


def test_upgrade_con_version_por_comandos_handler_la_fija(entorno, monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import fiscalberry.common.ComandosHandler as CH

    cfg = FakeConfig()
    monkeypatch.setattr(service, "_active", service.UpdaterService(config=cfg))

    resp = CH.ComandosHandler().send_command({"upgrade": {"version": "3.7.1"}})
    _esperar_remoto()

    assert "err" not in resp
    assert resp["rta"]["rta"]["target"] == "3.7.1"
    assert cfg.valores["pinned_version"] == "3.7.1"


def test_upgrade_con_version_basura_devuelve_error_claro_sin_lanzar(entorno, monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import fiscalberry.common.ComandosHandler as CH

    monkeypatch.setattr(service, "_active", service.UpdaterService(config=FakeConfig()))

    resp = CH.ComandosHandler().send_command({"upgrade": {"version": "3.7.1; rm -rf /"}})

    assert "no es una versión válida" in resp["err"]
    assert entorno.consultas == []


def test_restart_sin_supervisor_devuelve_error_explicito(monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import fiscalberry.common.ComandosHandler as CH

    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.setattr(CH.ComandosHandler, "_app_gui_en_ejecucion",
                        staticmethod(lambda: None))

    resp = CH.ComandosHandler().send_command({"restart": True})

    assert "no hay quién vuelva a levantar" in resp["err"]


def test_reboot_llama_a_rebootFiscalberry(monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import subprocess
    import fiscalberry.common.ComandosHandler as CH

    llamadas = []
    monkeypatch.setattr(subprocess, "call", lambda cmd: llamadas.append(cmd) or 0)

    resp = CH.ComandosHandler().send_command({"reboot": True})

    assert "err" not in resp
    assert llamadas == [["reboot"]]
    assert resp["rta"]["rta"] == 0
