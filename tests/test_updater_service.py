# coding=utf-8
"""
La decisión: qué hace el dispositivo con lo que encuentra publicado.

Estos son los tests que importan de verdad, porque codifican las dos reglas
que hacen que esto sea usable en un local real:

1. Se instala **lo que dice latest**, aunque sea una versión MENOR. Así,
   borrar un release malo revierte la flota entera sin tocar un dispositivo.
2. Nunca se actualiza con impresiones pendientes, y nunca se instala un
   binario que no pasó el selftest o que no se pudo verificar.
"""

import pytest

from fiscalberry.common.updater import (
    install_kind,
    release_source,
    service,
    staging,
)
from fiscalberry.version import VERSION


ASSET_CLI = "fiscalberry-linux-cli.tar.gz"


class Registro:
    """Anota si se llegó a aplicar algo, y con qué."""

    def __init__(self):
        self.aplicado = None
        self.reinicios = 0


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """
    Simula una instalación Linux-CLI empaquetada, con la cola vacía y todo
    listo para aplicar. Cada test rompe una sola pieza.
    """
    reg = Registro()

    destino = tmp_path / "fiscalberry-cli"
    destino.write_bytes(b"binario viejo")

    monkeypatch.setattr(install_kind, "detect", lambda: install_kind.LINUX_CLI)
    monkeypatch.setattr(install_kind, "current_executable",
                        lambda kind: str(destino))
    monkeypatch.setattr(service, "spooler_idle", lambda: True)

    monkeypatch.setattr(staging, "new_staging", lambda **kw: str(tmp_path / "st"))
    monkeypatch.setattr(staging, "cleanup", lambda p: None)
    monkeypatch.setattr(staging, "download",
                        lambda url, dest, sha, **kw: dest)
    monkeypatch.setattr(staging, "extract", lambda a, d: d)
    monkeypatch.setattr(staging, "find_binary",
                        lambda raiz, nombre: str(tmp_path / "nuevo"))

    monkeypatch.setattr(service.selftest, "run",
                        lambda binario, expected_version=None: (True, "ok"))

    def fake_apply(kind, **kwargs):
        reg.aplicado = kwargs
        return True

    monkeypatch.setattr(service.appliers, "apply_for_kind", fake_apply)
    monkeypatch.setattr(service.UpdaterService, "_pedir_reinicio",
                        lambda self: setattr(reg, "reinicios", reg.reinicios + 1))

    (tmp_path / "st").mkdir(exist_ok=True)
    return reg


def _publicar(monkeypatch, version, assets=(ASSET_CLI,), con_sums=True):
    rel = release_source.Release(
        tag=f"v{version}",
        version=version,
        assets={a: {"url": f"https://x/{a}", "size": 10} for a in assets},
    )
    monkeypatch.setattr(release_source, "fetch_latest",
                        lambda repo=None, session=None: rel)
    sums = {a: "0" * 64 for a in assets} if con_sums else {}
    monkeypatch.setattr(release_source, "fetch_checksums",
                        lambda release, session=None: sums)
    return rel


def test_si_ya_corre_la_version_vigente_no_hace_nada(entorno, monkeypatch):
    _publicar(monkeypatch, VERSION)

    estado, _ = service.UpdaterService().check_once()

    assert estado == "al-dia"
    assert entorno.aplicado is None


def test_instala_una_version_mayor(entorno, monkeypatch):
    _publicar(monkeypatch, "99.0.0")

    estado, detalle = service.UpdaterService().check_once()

    assert estado == "aplicado"
    assert detalle == "99.0.0"
    assert entorno.aplicado["version"] == "99.0.0"
    assert entorno.reinicios == 1


def test_vuelve_atras_si_latest_es_una_version_menor(entorno, monkeypatch):
    """
    El botón de pánico: se borró el release malo y GitHub volvió a apuntar al
    anterior. El dispositivo tiene que BAJAR, no quedarse donde está.
    """
    _publicar(monkeypatch, "0.0.1")

    estado, detalle = service.UpdaterService().check_once()

    assert estado == "aplicado"
    assert detalle == "0.0.1"
    assert entorno.aplicado["version"] == "0.0.1"
    assert entorno.aplicado["version_previa"] == VERSION


def test_release_sin_artefacto_para_mi_plataforma_no_es_error(entorno, monkeypatch):
    """
    Pasa de verdad: el build de Android es best-effort y la CI publica el
    release igual si falla. Para ese dispositivo simplemente no hay nada.
    """
    _publicar(monkeypatch, "99.0.0", assets=("fiscalberry-windows-cli.zip",))

    estado, _ = service.UpdaterService().check_once()

    assert estado == "sin-artefacto"
    assert entorno.aplicado is None


def test_sin_checksums_publicados_no_instala(entorno, monkeypatch):
    """Preferimos quedarnos viejos antes que instalar algo sin verificar."""
    _publicar(monkeypatch, "99.0.0", con_sums=False)

    estado, _ = service.UpdaterService().check_once()

    assert estado == "sin-checksums"
    assert entorno.aplicado is None


def test_no_actualiza_con_impresiones_pendientes(entorno, monkeypatch):
    """Actualizar con un ticket en la cola es perder el ticket."""
    _publicar(monkeypatch, "99.0.0")
    monkeypatch.setattr(service, "spooler_idle", lambda: False)

    estado, _ = service.UpdaterService().check_once()

    assert estado == "ocupado"
    assert entorno.aplicado is None


def test_binario_que_no_pasa_el_selftest_se_descarta(entorno, monkeypatch):
    """El caso que justifica todo el mecanismo: compila pero no arranca."""
    _publicar(monkeypatch, "99.0.0")
    monkeypatch.setattr(
        service.selftest, "run",
        lambda binario, expected_version=None: (False, "falta un import"))

    estado, detalle = service.UpdaterService().check_once()

    assert estado == "descartado"
    assert "import" in detalle
    assert entorno.aplicado is None
    assert entorno.reinicios == 0


def test_el_selftest_corre_antes_de_chequear_la_cola(entorno, monkeypatch):
    """
    Orden deliberado: probar el binario es barato y no toca nada; si va a
    fallar, mejor descubrirlo sin haber esperado a que se vacíe la cola.
    """
    orden = []
    _publicar(monkeypatch, "99.0.0")
    monkeypatch.setattr(service.selftest, "run",
                        lambda b, expected_version=None: (orden.append("selftest"), (True, "ok"))[1])
    monkeypatch.setattr(service, "spooler_idle",
                        lambda: (orden.append("cola"), True)[1])

    service.UpdaterService().check_once()

    assert orden == ["selftest", "cola"]


def test_github_caido_no_rompe_nada(entorno, monkeypatch):
    def explota(repo=None, session=None):
        raise release_source.ReleaseUnavailable("sin red")

    monkeypatch.setattr(release_source, "fetch_latest", explota)

    estado, _ = service.UpdaterService().check_once()

    assert estado == "error"
    assert entorno.aplicado is None


def test_se_puede_desactivar_por_configuracion():
    class ConfigFalsa:
        def get(self, seccion, clave, fallback=None):
            return "false" if clave == "enabled" else fallback

    svc = service.UpdaterService(config=ConfigFalsa())

    assert svc.enabled() is False
    assert svc.start() is None


def test_el_intervalo_tiene_un_piso():
    """Un intervalo absurdo no debe convertirse en un martilleo a GitHub."""
    class ConfigFalsa:
        def get(self, seccion, clave, fallback=None):
            return "0.0001" if clave == "check_interval_hours" else fallback

    assert service.UpdaterService(config=ConfigFalsa()).interval_seconds() >= 600
