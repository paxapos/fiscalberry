# coding=utf-8
"""
Actualización pedida desde paxapos (comando remoto 'upgrade').

Reglas que se fijan acá:

1. `{"upgrade": true}` dispara un chequeo YA, sin esperar las 6 h del loop.
2. `{"upgrade": {"version": "x.y.z"}}` FIJA esa versión: el chequeo (el pedido y
   los periódicos de después) apunta a ese tag y no a latest. Así se prueba un
   release en un local antes que en la flota sin que el loop lo pise.
3. `{"upgrade": {"version": "latest"}}` quita el pin.
4. Una versión con formato raro se rechaza (va a parar a una URL de GitHub).
5. El comando ya no explota: antes llamaba a `fbApp.upgradeGitPull()`, que no
   existía, y fallaba siempre.
"""

import threading

import pytest

from fiscalberry.common.updater import install_kind, release_source, service, staging
from fiscalberry.version import VERSION

ASSET_CLI = "fiscalberry-linux-cli.tar.gz"


class FakeConfig:
    """Lo mínimo de Configberry que usa el updater."""

    def __init__(self, valores=None):
        self.data = {"Updater": dict(valores or {})}

    def get(self, section, key, fallback=None):
        return self.data.get(section, {}).get(key, fallback)

    def set(self, section, kwargs):
        self.data.setdefault(section, {}).update(kwargs)
        return True


def _release(version):
    return release_source.Release(
        tag=f"v{version}", version=version,
        assets={ASSET_CLI: {"url": f"https://x/{ASSET_CLI}", "size": 10}})


@pytest.fixture
def consultas(monkeypatch, tmp_path):
    """Registra qué se le preguntó a GitHub; no aplica nada de verdad."""
    reg = {"latest": 0, "tags": [], "aplicado": None}

    def fake_latest(repo=None, session=None):
        reg["latest"] += 1
        return _release(VERSION)

    def fake_tag(version, repo=None, session=None):
        reg["tags"].append(version)
        return _release(version)

    monkeypatch.setattr(release_source, "fetch_latest", fake_latest)
    monkeypatch.setattr(release_source, "fetch_tag", fake_tag)
    monkeypatch.setattr(release_source, "fetch_checksums",
                        lambda release, session=None: {ASSET_CLI: "0" * 64})
    monkeypatch.setattr(install_kind, "detect", lambda: install_kind.LINUX_CLI)
    monkeypatch.setattr(install_kind, "current_app_dir", lambda kind: str(tmp_path))
    monkeypatch.setattr(service, "spooler_idle", lambda: True)
    monkeypatch.setattr(staging, "new_staging", lambda **kw: str(tmp_path))
    monkeypatch.setattr(staging, "cleanup", lambda p: None)
    monkeypatch.setattr(staging, "cleanup_stale", lambda: None)
    monkeypatch.setattr(staging, "download", lambda url, dest, sha, **kw: dest)
    monkeypatch.setattr(staging, "extract", lambda a, d: d)
    monkeypatch.setattr(staging, "find_app_dir", lambda r, n, b: str(tmp_path))
    monkeypatch.setattr(service.selftest, "run",
                        lambda binario, expected_version=None: (True, "ok"))

    def fake_apply(kind, **kwargs):
        reg["aplicado"] = kwargs["version"]
        return True

    monkeypatch.setattr(service.appliers, "apply_for_kind", fake_apply)
    monkeypatch.setattr(service.UpdaterService, "_pedir_reinicio", lambda self: None)
    monkeypatch.setattr(service, "_active", None)
    return reg


def _esperar(updater):
    for t in threading.enumerate():
        if t.name == "fiscalberry-updater-remoto":
            t.join(timeout=5)


def test_sin_pin_sigue_a_latest(consultas):
    estado, _ = service.UpdaterService(config=FakeConfig()).check_once()

    assert estado == "al-dia"
    assert consultas["latest"] == 1
    assert consultas["tags"] == []


def test_con_pin_consulta_ese_tag_y_lo_aplica(consultas):
    cfg = FakeConfig({"pinned_version": "3.5.2"})

    estado, detalle = service.UpdaterService(config=cfg).check_once()

    assert (estado, detalle) == ("aplicado", "3.5.2")
    assert consultas["tags"] == ["3.5.2"]
    assert consultas["latest"] == 0


def test_pin_invalido_en_config_se_ignora(consultas):
    cfg = FakeConfig({"pinned_version": "../../evil"})

    service.UpdaterService(config=cfg).check_once()

    assert consultas["tags"] == []
    assert consultas["latest"] == 1


def test_request_check_fija_la_version_y_chequea_ya(consultas):
    cfg = FakeConfig()
    up = service.UpdaterService(config=cfg)

    rta = up.request_check("v99.1.0")
    _esperar(up)

    assert rta == {"accepted": True, "current": VERSION, "target": "99.1.0"}
    assert cfg.data["Updater"]["pinned_version"] == "99.1.0"
    assert consultas["aplicado"] == "99.1.0"


def test_latest_quita_el_pin(consultas):
    cfg = FakeConfig({"pinned_version": "3.5.2"})
    up = service.UpdaterService(config=cfg)

    rta = up.request_check("latest")
    _esperar(up)

    assert rta["target"] == "latest"
    assert cfg.data["Updater"]["pinned_version"] == ""
    assert consultas["latest"] == 1


def test_version_con_formato_invalido_se_rechaza(consultas):
    up = service.UpdaterService(config=FakeConfig())

    with pytest.raises(service.InvalidVersion):
        up.request_check("3.6; rm -rf /")


def test_no_corren_dos_chequeos_a_la_vez(consultas):
    up = service.UpdaterService(config=FakeConfig())
    up._check_lock.acquire()
    try:
        assert up.check_once() == ("ocupado", "ya hay un chequeo en curso")
    finally:
        up._check_lock.release()


def test_request_remote_update_usa_el_updater_activo(consultas):
    cfg = FakeConfig()
    up = service.UpdaterService(config=cfg)
    service._active = up

    rta = service.request_remote_update("99.2.0")
    _esperar(up)

    assert rta["target"] == "99.2.0"
    assert cfg.data["Updater"]["pinned_version"] == "99.2.0"


def test_request_remote_update_sin_updater_activo_arma_uno(consultas):
    cfg = FakeConfig()

    rta = service.request_remote_update(None, config=cfg)

    assert rta["accepted"] is True
    assert rta["target"] == "latest"


class TestComandoUpgrade:
    """El comando tal como llega por MQTT/SIO a ComandosHandler."""

    @pytest.fixture(autouse=True)
    def _handler(self, monkeypatch):
        pytest.importorskip("paho")
        pytest.importorskip("escpos")
        import fiscalberry.common.ComandosHandler as CH
        self.CH = CH
        self.llamadas = []

        def fake_remote(version=None, config=None):
            self.llamadas.append(version)
            return {"accepted": True, "target": version or "latest"}

        monkeypatch.setattr(service, "request_remote_update", fake_remote)

    def test_upgrade_true_chequea_sin_cambiar_el_pin(self):
        rta = self.CH.ComandosHandler().send_command({"upgrade": True})

        assert "err" not in rta
        assert self.llamadas == [None]
        assert rta["rta"]["action"] == "upgrade"

    def test_upgrade_con_version(self):
        rta = self.CH.ComandosHandler().send_command({"upgrade": {"version": "3.7.0"}})

        assert self.llamadas == ["3.7.0"]
        assert rta["rta"]["rta"]["target"] == "3.7.0"
