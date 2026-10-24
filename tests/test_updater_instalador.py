# coding=utf-8
"""
Actualizar la GUI de Windows con FiscalberrySetup.exe.

El updater del zip reemplazaba la carpeta entera y se llevaba puesto
`unins000.exe`: la entrada en "Aplicaciones" quedaba rota y con la versión
vieja. Ahora la GUI de Windows corre el setup nuevo en silencio, que pisa la
versión anterior completa, y se cierra para soltar el mutex.

Lo que fijan estos tests:

- La línea de comandos exacta del setup (silencioso, sin reinicio, relanza).
- Antes de instalar se guarda el setup de la versión actual, verificado: es el
  respaldo para revertir. Sin él se actualiza igual y queda en el log.
- Si la versión nueva no confirma el arranque, se reinstala la anterior.
- Una versión revertida no se vuelve a instalar en loop.
"""

import hashlib
import os

import pytest

from fiscalberry.common.updater import (
    appliers,
    commit_guard,
    install_kind,
    installer,
    release_source,
    service,
    staging,
)
from fiscalberry.version import VERSION

NUEVA = "99.0.0"
SETUP = "FiscalberrySetup.exe"


@pytest.fixture
def aislado(monkeypatch, tmp_path):
    """Estado del updater, setups guardados y logs dentro de tmp_path."""
    monkeypatch.setattr(commit_guard, "_state_path",
                        lambda: str(tmp_path / "update_pending.json"))
    carpeta = tmp_path / "installer"
    carpeta.mkdir()
    monkeypatch.setattr(installer, "installer_dir", lambda: str(carpeta))
    monkeypatch.setattr(installer, "log_path", lambda v: str(tmp_path / f"instalador-{v}.log"))
    lanzados = []
    monkeypatch.setattr(installer, "lanzar_setup", lambda args: lanzados.append(args))
    return tmp_path, carpeta, lanzados


# --------------------------------------------------------------------------
# La línea de comandos
# --------------------------------------------------------------------------

def test_linea_de_comandos_del_setup_silencioso():
    args = installer.setup_command(r"C:\datos\FiscalberrySetup-3.7.0.exe",
                                   log=r"C:\Users\Juan Perez\logs\instalador.log")
    assert args == [
        r"C:\datos\FiscalberrySetup-3.7.0.exe",
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
        "/RELAUNCH=1",
        r"/LOG=C:\Users\Juan Perez\logs\instalador.log",
    ]


def test_sin_log_ni_relanzar():
    assert installer.setup_command("s.exe", relanzar=False) == [
        "s.exe", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
        "/CLOSEAPPLICATIONS"]


def test_el_setup_se_lanza_fuera_de_la_instalacion_y_con_espera_del_candado(
        monkeypatch):
    capturado = {}

    def popen(args, **kwargs):
        capturado.update(kwargs, args=args)

    monkeypatch.setattr(installer.subprocess, "Popen", popen)
    installer.lanzar_setup(["s.exe", "/VERYSILENT"])

    assert capturado["args"] == ["s.exe", "/VERYSILENT"]
    assert capturado["cwd"] == installer.tempfile.gettempdir()
    # El Fiscalberry que relanza el setup espera al mutex en vez de rendirse.
    assert capturado["env"]["FISCALBERRY_LOCK_WAIT"] == appliers.RELAUNCH_LOCK_WAIT


# --------------------------------------------------------------------------
# El respaldo: el setup de la versión que está corriendo
# --------------------------------------------------------------------------

def _sums_del_tag(contenido=b"setup de la version actual", con_setup=True):
    """El SHA256SUMS del release de la versión actual."""
    sums = {"fiscalberry-windows-gui.zip": "1" * 64}
    if con_setup:
        sums[SETUP] = hashlib.sha256(contenido).hexdigest()
    return sums, contenido


def _descarga_falsa(contenido, registro):
    def download(url, destino, esperado, **kw):
        registro.append(url)
        with open(destino, "wb") as fh:
            fh.write(contenido)
        if hashlib.sha256(contenido).hexdigest() != esperado:
            raise staging.StagingError("checksum no coincide")
        return destino
    return download


def _checksums_de(sums, pedidos):
    def fetch_checksums(release, session=None):
        pedidos.append(release)
        return sums
    return fetch_checksums


def test_guarda_y_verifica_el_setup_de_la_version_actual(aislado, monkeypatch):
    _tmp, carpeta, _ = aislado
    sums, contenido = _sums_del_tag()
    releases = []
    monkeypatch.setattr(release_source, "fetch_checksums", _checksums_de(sums, releases))
    bajadas = []
    monkeypatch.setattr(staging, "download", _descarga_falsa(contenido, bajadas))

    ruta = installer.preparar_respaldo(VERSION)

    assert releases[0].tag == f"v{VERSION}"
    assert bajadas == [
        f"https://github.com/paxapos/fiscalberry/releases/download/v{VERSION}/{SETUP}"]
    assert ruta == os.path.join(str(carpeta), f"FiscalberrySetup-{VERSION}.exe")
    assert open(ruta, "rb").read() == contenido
    assert not os.path.exists(ruta + ".part")

    # La segunda vez no se vuelve a bajar: el archivo guardado ya verifica.
    assert installer.preparar_respaldo(VERSION) == ruta
    assert len(bajadas) == 1


def test_version_publicada_sin_instalador_no_tiene_respaldo(aislado, monkeypatch, caplog):
    sums, _ = _sums_del_tag(con_setup=False)
    monkeypatch.setattr(release_source, "fetch_checksums", _checksums_de(sums, []))
    bajadas = []
    monkeypatch.setattr(staging, "download", _descarga_falsa(b"x", bajadas))

    assert installer.preparar_respaldo(VERSION) is None
    assert bajadas == []
    assert "no publicó FiscalberrySetup.exe" in caplog.text


def test_un_setup_que_no_verifica_no_queda_guardado(aislado, monkeypatch):
    _tmp, carpeta, _ = aislado
    sums, _ = _sums_del_tag(contenido=b"el bueno")
    monkeypatch.setattr(release_source, "fetch_checksums", _checksums_de(sums, []))
    monkeypatch.setattr(staging, "download", _descarga_falsa(b"adulterado", []))

    assert installer.preparar_respaldo(VERSION) is None
    assert os.listdir(str(carpeta)) == []


def test_github_caido_no_impide_actualizar(aislado, monkeypatch):
    # fetch_checksums devuelve {} cuando no puede bajar el SHA256SUMS.
    monkeypatch.setattr(release_source, "fetch_checksums", _checksums_de({}, []))
    assert installer.preparar_respaldo(VERSION) is None


# --------------------------------------------------------------------------
# Aplicar
# --------------------------------------------------------------------------

def _setup_descargado(tmp_path, contenido=b"setup nuevo"):
    st = tmp_path / "staging"
    st.mkdir(exist_ok=True)
    ruta = st / SETUP
    ruta.write_bytes(contenido)
    return str(ruta)


def test_aplicar_lanza_el_setup_y_arma_la_reversion(aislado):
    tmp_path, carpeta, lanzados = aislado
    respaldo = carpeta / f"FiscalberrySetup-{VERSION}.exe"
    respaldo.write_bytes(b"setup actual")
    (carpeta / "FiscalberrySetup-1.0.0.exe").write_bytes(b"uno viejo")

    installer.aplicar(_setup_descargado(tmp_path), r"C:\Programs\Fiscalberry",
                      NUEVA, VERSION, str(respaldo))

    copia = os.path.join(str(carpeta), f"FiscalberrySetup-{NUEVA}.exe")
    assert lanzados == [installer.setup_command(copia, installer.log_path(NUEVA))]
    # Sobrevive al staging, y queda como respaldo de la próxima actualización.
    assert open(copia, "rb").read() == b"setup nuevo"
    # Los setups que ya no sirven se limpian; el respaldo no.
    assert sorted(os.listdir(str(carpeta))) == sorted([
        f"FiscalberrySetup-{NUEVA}.exe", f"FiscalberrySetup-{VERSION}.exe"])

    pendiente = commit_guard.read()
    assert pendiente.method == commit_guard.METODO_INSTALADOR
    assert (pendiente.version, pendiente.previous_version) == (NUEVA, VERSION)
    assert pendiente.backup == str(respaldo)


def test_aplicar_sin_respaldo_actualiza_igual_y_lo_deja_en_el_log(aislado, caplog):
    tmp_path, _carpeta, lanzados = aislado

    installer.aplicar(_setup_descargado(tmp_path), r"C:\inst", NUEVA, VERSION, None)

    assert len(lanzados) == 1
    assert "SIN reversión local" in caplog.text
    assert commit_guard.read().backup is None


def test_si_no_se_puede_lanzar_el_setup_no_queda_marca(aislado, monkeypatch):
    tmp_path, _carpeta, _ = aislado

    def no_lanza(args):
        raise OSError("acceso denegado")

    monkeypatch.setattr(installer, "lanzar_setup", no_lanza)
    with pytest.raises(appliers.ApplyError):
        installer.aplicar(_setup_descargado(tmp_path), r"C:\inst", NUEVA, VERSION, None)
    assert commit_guard.read() is None


# --------------------------------------------------------------------------
# Revertir
# --------------------------------------------------------------------------

def test_revertir_reinstala_el_setup_anterior_y_no_reintenta_la_nueva(aislado):
    _tmp, carpeta, lanzados = aislado
    respaldo = carpeta / f"FiscalberrySetup-{VERSION}.exe"
    respaldo.write_bytes(b"setup actual")
    commit_guard.arm(NUEVA, VERSION, r"C:\inst", str(respaldo),
                     method=commit_guard.METODO_INSTALADOR)

    assert appliers.rollback(commit_guard.read()) is True

    assert lanzados == [installer.setup_command(str(respaldo), installer.log_path(VERSION))]
    assert commit_guard.read() is None
    assert commit_guard.reverted_version() == NUEVA


def test_revertir_sin_setup_anterior_no_puede_y_lo_dice(aislado, caplog):
    _tmp, _carpeta, lanzados = aislado
    commit_guard.arm(NUEVA, VERSION, r"C:\inst", None,
                     method=commit_guard.METODO_INSTALADOR)

    assert appliers.rollback(commit_guard.read()) is False

    assert lanzados == []
    assert commit_guard.read() is None
    assert "no se puede revertir" in caplog.text


def test_tras_tres_arranques_sin_confirmar_se_reinstala_la_anterior(aislado, monkeypatch):
    _tmp, carpeta, lanzados = aislado
    respaldo = carpeta / f"FiscalberrySetup-{VERSION}.exe"
    respaldo.write_bytes(b"setup actual")
    commit_guard.arm(NUEVA, VERSION, r"C:\inst", str(respaldo),
                     method=commit_guard.METODO_INSTALADOR)
    salidas = []
    monkeypatch.setattr(service.os, "_exit", lambda codigo: salidas.append(codigo))

    for _ in range(commit_guard.MAX_BOOTS):
        service.on_process_start()
    assert lanzados == [] and salidas == []

    service.on_process_start()
    assert len(lanzados) == 1 and lanzados[0][0] == str(respaldo)
    assert salidas == [0]


# --------------------------------------------------------------------------
# El ciclo completo del updater
# --------------------------------------------------------------------------

@pytest.fixture
def gui_windows(aislado, monkeypatch):
    tmp_path, carpeta, lanzados = aislado
    monkeypatch.setattr(install_kind, "detect", lambda: install_kind.WINDOWS_INSTALLER)
    monkeypatch.setattr(install_kind, "current_app_dir",
                        lambda kind: r"C:\Users\x\AppData\Local\Programs\Fiscalberry")
    monkeypatch.setattr(service, "spooler_idle", lambda: True)
    monkeypatch.setattr(staging, "new_staging", lambda **kw: str(tmp_path / "staging"))
    monkeypatch.setattr(staging, "cleanup_stale", lambda: 0)
    limpiados = []
    monkeypatch.setattr(staging, "cleanup", lambda p: limpiados.append(p))

    def download(url, destino, esperado, **kw):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "wb") as fh:
            fh.write(b"setup nuevo")
        return destino

    monkeypatch.setattr(staging, "download", download)

    rel = release_source.Release(tag=f"v{NUEVA}", version=NUEVA,
                                 assets={SETUP: {"url": "https://x/s", "size": 11}})
    monkeypatch.setattr(release_source, "fetch_latest", lambda repo=None, session=None: rel)
    monkeypatch.setattr(release_source, "fetch_checksums",
                        lambda r, session=None: {SETUP: "0" * 64})

    respaldo = carpeta / f"FiscalberrySetup-{VERSION}.exe"
    respaldo.write_bytes(b"setup actual")
    monkeypatch.setattr(installer, "preparar_respaldo",
                        lambda version, repo=None: str(respaldo))

    def no_debe_correr(*a, **kw):
        raise AssertionError("un setup no se prueba con --selftest")

    monkeypatch.setattr(service.selftest, "run", no_debe_correr)

    reinicios = []
    monkeypatch.setattr(service.UpdaterService, "_pedir_reinicio",
                        lambda self: reinicios.append(1))
    return lanzados, reinicios, str(respaldo)


def test_la_gui_de_windows_se_actualiza_con_el_instalador(gui_windows):
    lanzados, reinicios, respaldo = gui_windows

    resultado = service.UpdaterService().check_once()

    assert resultado == ("aplicado", NUEVA)
    assert len(lanzados) == 1 and lanzados[0][1:6] == [
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
        "/RELAUNCH=1"]
    # Este proceso se cierra para soltar el mutex que espera el setup.
    assert reinicios == [1]
    assert commit_guard.read().backup == respaldo


def test_con_la_cola_ocupada_no_instala(gui_windows, monkeypatch):
    lanzados, reinicios, _ = gui_windows
    monkeypatch.setattr(service, "spooler_idle", lambda: False)

    assert service.UpdaterService().check_once()[0] == "ocupado"
    assert lanzados == [] and reinicios == []
    assert commit_guard.read() is None


def test_una_version_revertida_no_se_vuelve_a_instalar(gui_windows):
    lanzados, reinicios, _ = gui_windows
    commit_guard.mark_reverted(NUEVA)

    assert service.UpdaterService().check_once() == ("revertida", NUEVA)
    assert lanzados == [] and reinicios == []


def test_si_sale_otra_version_se_instala_aunque_haya_una_revertida(gui_windows):
    lanzados, _reinicios, _ = gui_windows
    commit_guard.mark_reverted("98.0.0")

    assert service.UpdaterService().check_once() == ("aplicado", NUEVA)
    assert len(lanzados) == 1


def test_la_reversion_por_carpeta_tambien_anota_la_version(aislado, tmp_path, monkeypatch):
    """Linux/Raspberry: un binario que no arranca tampoco se reinstala en loop."""
    destino = tmp_path / "inst" / "fiscalberry-cli"
    respaldo = tmp_path / "inst" / "fiscalberry-cli.fb-backup"
    destino.mkdir(parents=True)
    respaldo.mkdir()
    (respaldo / "fiscalberry-cli").write_bytes(b"version anterior")
    commit_guard.arm(NUEVA, VERSION, str(destino), str(respaldo))

    monkeypatch.setattr(appliers, "_es_windows", lambda: False)
    assert appliers.rollback(commit_guard.read()) is True

    assert commit_guard.reverted_version() == NUEVA
    assert (destino / "fiscalberry-cli").read_bytes() == b"version anterior"
