# coding=utf-8
"""
Actualización de la GUI de Windows con el instalador de Inno Setup (#187).

Las promesas que se fijan acá:

1. La actualización siempre pasa por FiscalberrySetup.exe, en silencio, con
   /RELAUNCH=1: pisa la versión anterior, mantiene el desinstalador al día y
   vuelve a abrir Fiscalberry en la bandeja.
2. Antes de aplicar, se guarda (verificado) el instalador de la versión que
   está corriendo. Si la nueva no confirma el arranque, se reinstala ese.
3. Las versiones anteriores al instalador no tienen con qué volver atrás: se
   actualiza igual y queda en el log.
4. Una versión que se revirtió no se vuelve a instalar en loop.
"""

import os

import pytest

from fiscalberry.common.updater import (
    appliers,
    commit_guard,
    install_kind,
    release_source,
    service,
    staging,
)
from fiscalberry.version import VERSION


SETUP = "FiscalberrySetup.exe"


@pytest.fixture(autouse=True)
def estado_aislado(monkeypatch, tmp_path):
    monkeypatch.setattr(commit_guard, "_state_path",
                        lambda: str(tmp_path / "estado" / "update_pending.json"))
    (tmp_path / "estado").mkdir()
    monkeypatch.setattr(staging, "rollback_dir", lambda: str(tmp_path / "rollback"))
    (tmp_path / "rollback").mkdir()
    monkeypatch.setattr(appliers, "installer_log_path",
                        lambda version, prefijo="instalador": str(tmp_path / f"{prefijo}-{version}.log"))


class PopenFalso:
    def __init__(self):
        self.llamadas = []

    def __call__(self, argv, **kwargs):
        self.llamadas.append((argv, kwargs))
        return object()


# ---------------------------------------------------------------------------
# Línea de comandos del setup
# ---------------------------------------------------------------------------

def test_el_setup_se_lanza_en_silencio_desacoplado_y_relanzando_la_app():
    popen = PopenFalso()

    appliers.launch_installer(r"C:\tmp\FiscalberrySetup.exe", r"C:\logs\instalador.log",
                              popen=popen)

    (argv, kwargs), = popen.llamadas
    assert argv == [
        r"C:\tmp\FiscalberrySetup.exe",
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/RELAUNCH=1",
        r"/LOG=C:\logs\instalador.log",
    ]
    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: el setup sobrevive a este
    # proceso, que tiene que salir para liberar el mutex.
    assert kwargs["creationflags"] == 0x00000008 | 0x00000200
    assert kwargs["close_fds"] is True


def test_aplicar_arma_la_reversion_con_el_setup_anterior(tmp_path):
    nuevo = tmp_path / "nuevo" / SETUP
    nuevo.parent.mkdir()
    nuevo.write_bytes(b"setup nuevo")
    anterior = tmp_path / "rollback" / "FiscalberrySetup-3.7.0.exe"
    anterior.write_bytes(b"setup anterior")
    popen = PopenFalso()

    appliers.apply_windows_installer(str(nuevo), "3.8.0", "3.7.0",
                                     rollback_setup=str(anterior), popen=popen)

    pend = commit_guard.read()
    assert pend.method == commit_guard.METHOD_INSTALLER
    assert pend.version == "3.8.0"
    assert pend.previous_version == "3.7.0"
    assert pend.backup == str(anterior)
    assert popen.llamadas[0][0][0] == str(nuevo)


def test_si_el_setup_no_se_puede_lanzar_no_queda_marca(tmp_path):
    nuevo = tmp_path / SETUP
    nuevo.write_bytes(b"setup")

    def popen_roto(argv, **kwargs):
        raise OSError("bloqueado por el antivirus")

    with pytest.raises(appliers.ApplyError):
        appliers.apply_windows_installer(str(nuevo), "3.8.0", "3.7.0", popen=popen_roto)

    assert commit_guard.read() is None


# ---------------------------------------------------------------------------
# Reversión al arrancar
# ---------------------------------------------------------------------------

def _agotar_arranques():
    for _ in range(commit_guard.MAX_BOOTS):
        commit_guard.register_boot(running_version="3.8.0")


def test_si_la_version_nueva_no_arranca_se_reinstala_la_anterior(tmp_path, monkeypatch):
    anterior = tmp_path / "rollback" / "FiscalberrySetup-3.7.0.exe"
    anterior.write_bytes(b"setup anterior")
    commit_guard.arm("3.8.0", "3.7.0", None, str(anterior),
                     method=commit_guard.METHOD_INSTALLER)
    _agotar_arranques()

    lanzados = []
    marca_al_lanzar = []

    def lanzar(setup, log_path, popen=None):
        marca_al_lanzar.append(commit_guard.read())
        lanzados.append(setup)

    salidas = []
    monkeypatch.setattr(appliers, "launch_installer", lanzar)
    monkeypatch.setattr(service, "VERSION", "3.8.0")
    monkeypatch.setattr(service.os, "_exit", lambda codigo: salidas.append(codigo))

    service.on_process_start()

    assert lanzados == [str(anterior)]
    # La marca ya no estaba al lanzar: la versión reinstalada no tiene que
    # contar arranques contra esta actualización (revertiría en loop).
    assert marca_al_lanzar == [None]
    assert salidas == [0]
    # Y la 3.8.0 queda descartada en este equipo.
    assert commit_guard.is_failed("3.8.0")
    assert not commit_guard.is_failed("3.9.0")


def test_sin_setup_anterior_no_hay_reversion_y_queda_en_el_log(monkeypatch, caplog):
    """Versiones anteriores al instalador (3.6.x): no hay a qué volver."""
    commit_guard.arm("3.8.0", "3.6.6", None, None, method=commit_guard.METHOD_INSTALLER)
    _agotar_arranques()

    monkeypatch.setattr(appliers, "launch_installer",
                        lambda *a, **k: pytest.fail("no hay setup para lanzar"))
    monkeypatch.setattr(service, "VERSION", "3.8.0")
    monkeypatch.setattr(service.os, "_exit", lambda codigo: pytest.fail("no debe salir"))

    with caplog.at_level("ERROR"):
        service.on_process_start()

    assert "no hay instalador de 3.6.6" in caplog.text
    assert commit_guard.read() is None


def test_si_sigue_corriendo_la_version_anterior_la_actualizacion_no_se_instalo():
    """El setup se canceló o falló: no hay nada que revertir."""
    commit_guard.arm("3.8.0", "3.7.0", None, "x", method=commit_guard.METHOD_INSTALLER)

    for _ in range(commit_guard.MAX_BOOTS + 2):
        pend, revertir = commit_guard.register_boot(running_version="3.7.0")
        assert pend is None and revertir is False

    assert commit_guard.read() is None


def test_las_marcas_viejas_sin_metodo_se_revierten_como_carpeta(tmp_path):
    import json
    ruta = commit_guard._state_path()
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"version": "3.6.6", "previous_version": "3.6.5",
                   "target": "t", "backup": "b", "boots": 0}, fh)

    assert commit_guard.read().method == commit_guard.METHOD_FOLDER


# ---------------------------------------------------------------------------
# El chequeo del updater en la GUI de Windows
# ---------------------------------------------------------------------------

class Registro:
    def __init__(self):
        self.aplicado = None
        self.reinicios = 0
        self.limpiados = []
        self.descargas = []


def _release(version, assets):
    return release_source.Release(
        tag=f"v{version}", version=version,
        assets={a: {"url": f"https://x/v{version}/{a}", "size": 10} for a in assets},
    )


@pytest.fixture
def gui_windows(monkeypatch, tmp_path):
    reg = Registro()
    monkeypatch.setattr(install_kind, "detect", lambda: install_kind.WINDOWS_INSTALLER)
    monkeypatch.setattr(install_kind, "current_app_dir",
                        lambda kind: r"C:\Users\x\AppData\Local\Programs\Fiscalberry")
    monkeypatch.setattr(service, "spooler_idle", lambda: True)

    staging_dir = tmp_path / "st"
    staging_dir.mkdir()
    monkeypatch.setattr(staging, "cleanup_stale", lambda: 0)
    monkeypatch.setattr(staging, "new_staging", lambda **kw: str(staging_dir))
    monkeypatch.setattr(staging, "cleanup", lambda p: reg.limpiados.append(p))

    def descargar(url, destino, sha, **kw):
        reg.descargas.append(url)
        with open(destino, "wb") as fh:
            fh.write(url.encode())
        return destino

    monkeypatch.setattr(staging, "download", descargar)
    monkeypatch.setattr(release_source, "fetch_checksums",
                        lambda release, session=None: {a: "0" * 64 for a in release.assets})

    def aplicar(kind, **kwargs):
        reg.aplicado = dict(kwargs, kind=kind)
        return True

    monkeypatch.setattr(service.appliers, "apply_for_kind", aplicar)
    monkeypatch.setattr(service.UpdaterService, "_pedir_reinicio",
                        lambda self: setattr(reg, "reinicios", reg.reinicios + 1))
    return reg


def _publicar(monkeypatch, nueva, actual=None):
    monkeypatch.setattr(release_source, "fetch_latest",
                        lambda repo=None, session=None: nueva)

    def por_tag(tag, repo=None, session=None):
        if actual is None or tag != actual.tag:
            raise release_source.ReleaseNotFound(tag)
        return actual

    monkeypatch.setattr(release_source, "fetch_release_by_tag", por_tag)


def test_actualiza_con_el_setup_y_guarda_el_de_la_version_actual(gui_windows, monkeypatch, tmp_path):
    _publicar(monkeypatch, _release("99.0.0", (SETUP, "SHA256SUMS")),
              actual=_release(VERSION, (SETUP, "SHA256SUMS")))

    estado, detalle = service.UpdaterService().check_once()

    assert (estado, detalle) == ("aplicado", "99.0.0")
    aplicado = gui_windows.aplicado
    assert aplicado["kind"] == install_kind.WINDOWS_INSTALLER
    assert aplicado["version"] == "99.0.0"
    assert aplicado["version_previa"] == VERSION
    assert aplicado["setup_path"].endswith(SETUP)
    # El instalador de la versión actual quedó guardado para volver a ella.
    respaldo = aplicado["rollback_setup"]
    assert respaldo == str(tmp_path / "rollback" / f"FiscalberrySetup-{VERSION}.exe")
    assert os.path.isfile(respaldo)
    assert f"https://x/v{VERSION}/{SETUP}" in gui_windows.descargas
    assert gui_windows.reinicios == 1
    # El setup se lee a sí mismo mientras instala: el staging no se borra.
    assert gui_windows.limpiados == []


def test_desde_una_version_anterior_al_instalador_actualiza_sin_reversion(gui_windows, monkeypatch, caplog):
    """3.6.x (zip portable): su release no trae FiscalberrySetup.exe."""
    _publicar(monkeypatch, _release("99.0.0", (SETUP,)),
              actual=_release(VERSION, ("fiscalberry-windows-gui.zip",)))

    with caplog.at_level("WARNING"):
        estado, _ = service.UpdaterService().check_once()

    assert estado == "aplicado"
    assert gui_windows.aplicado["rollback_setup"] is None
    assert "anterior al instalador" in caplog.text


def test_sin_release_de_la_version_actual_actualiza_sin_reversion(gui_windows, monkeypatch):
    """Un build de desarrollo, o un release que se borró."""
    _publicar(monkeypatch, _release("99.0.0", (SETUP,)), actual=None)

    estado, _ = service.UpdaterService().check_once()

    assert estado == "aplicado"
    assert gui_windows.aplicado["rollback_setup"] is None


def test_si_el_setup_de_reversion_no_se_puede_bajar_no_se_actualiza(gui_windows, monkeypatch):
    """Existe con qué volver atrás pero no llegó: se reintenta más tarde."""
    _publicar(monkeypatch, _release("99.0.0", (SETUP,)),
              actual=_release(VERSION, (SETUP,)))

    def descarga_rota(url, destino, sha, **kw):
        if f"v{VERSION}" in url:
            raise staging.StagingError("checksum no coincide")
        with open(destino, "wb") as fh:
            fh.write(b"x")
        return destino

    monkeypatch.setattr(staging, "download", descarga_rota)

    estado, _ = service.UpdaterService().check_once()

    assert estado == "error"
    assert gui_windows.aplicado is None
    assert gui_windows.reinicios == 0


def test_si_github_no_responde_por_la_version_actual_no_se_actualiza(gui_windows, monkeypatch):
    _publicar(monkeypatch, _release("99.0.0", (SETUP,)))

    def caido(tag, repo=None, session=None):
        raise release_source.ReleaseUnavailable("timeout")

    monkeypatch.setattr(release_source, "fetch_release_by_tag", caido)

    estado, _ = service.UpdaterService().check_once()

    assert estado == "error"
    assert gui_windows.aplicado is None


def test_con_impresiones_pendientes_no_se_actualiza(gui_windows, monkeypatch):
    _publicar(monkeypatch, _release("99.0.0", (SETUP,)))
    monkeypatch.setattr(service, "spooler_idle", lambda: False)

    estado, _ = service.UpdaterService().check_once()

    assert estado == "ocupado"
    assert gui_windows.aplicado is None


def test_una_version_que_ya_fallo_no_se_reinstala(gui_windows, monkeypatch):
    _publicar(monkeypatch, _release("99.0.0", (SETUP,)))
    commit_guard.remember_failed("99.0.0")

    estado, _ = service.UpdaterService().check_once()

    assert estado == "descartado"
    assert gui_windows.aplicado is None
    assert gui_windows.descargas == []


def test_se_borran_los_setups_de_reversion_que_ya_no_sirven(gui_windows, monkeypatch, tmp_path):
    viejo = tmp_path / "rollback" / "FiscalberrySetup-3.1.0.exe"
    viejo.write_bytes(b"viejo")
    _publicar(monkeypatch, _release("99.0.0", (SETUP,)),
              actual=_release(VERSION, (SETUP,)))

    service.UpdaterService().check_once()

    assert not viejo.exists()
    assert (tmp_path / "rollback" / f"FiscalberrySetup-{VERSION}.exe").exists()


# ---------------------------------------------------------------------------
# Copias portables que quedaron después de migrar
# ---------------------------------------------------------------------------

from fiscalberry.desktop.main import redirect_portable_to_installed  # noqa: E402


@pytest.fixture
def instalada(tmp_path):
    carpeta = tmp_path / "Programs" / "Fiscalberry"
    carpeta.mkdir(parents=True)
    (carpeta / "fiscalberry-gui.exe").write_bytes(b"exe")
    portable = tmp_path / "Descargas" / "fiscalberry-gui"
    portable.mkdir(parents=True)
    (portable / "fiscalberry-gui.exe").write_bytes(b"exe viejo")
    return carpeta, portable / "fiscalberry-gui.exe"


def test_la_copia_portable_abre_la_instalada(instalada):
    carpeta, portable = instalada
    popen = PopenFalso()

    assert redirect_portable_to_installed(
        start_minimized=True, platform="win32", frozen=True,
        executable=str(portable), location=str(carpeta), popen=popen) is True

    (argv, kwargs), = popen.llamadas
    assert argv == [str(carpeta / "fiscalberry-gui.exe"), "--minimized"]
    assert kwargs["creationflags"] == 0x00000008 | 0x00000200


def test_la_instalada_arranca_normalmente(instalada):
    carpeta, _ = instalada
    assert redirect_portable_to_installed(
        platform="win32", frozen=True,
        executable=str(carpeta / "fiscalberry-gui.exe"), location=str(carpeta),
        popen=lambda *a, **k: pytest.fail("no debe relanzar")) is False


@pytest.mark.parametrize("platform,frozen,con_instalacion", [
    ("linux", True, True),      # Linux no tiene instalador
    ("win32", False, True),     # desde el código fuente
    ("win32", True, False),     # portable sin instalación: sigue como siempre
])
def test_sin_instalacion_o_fuera_de_windows_no_redirige(instalada, platform, frozen, con_instalacion):
    carpeta, portable = instalada
    assert redirect_portable_to_installed(
        platform=platform, frozen=frozen, executable=str(portable),
        location=str(carpeta) if con_instalacion else "",
        popen=lambda *a, **k: pytest.fail("no debe relanzar")) is False
