# coding=utf-8
"""
El reemplazo de la instalación en Windows (ayudante `--apply-update`).

Bug que fijan estos tests: Fiscalberry se cerraba solo a los 5 minutos de
abrirlo y no volvía. El updater lanzaba al ayudante sin darle carpeta de
trabajo, así que heredaba la del programa, que al abrirlo desde un acceso
directo o con doble clic ES la carpeta de instalación. Windows no deja renombrar
la carpeta actual de un proceso vivo: el ayudante no podía apartar la
instalación, cancelaba y no relanzaba nada. Al volver a abrir, la versión vieja
repetía todo a los 5 minutos.

Estos tests corren en Linux, donde esa regla no existe, así que se simula:
`os.rename` falla si la carpeta a mover contiene a la cwd, igual que en Windows.
"""

import os

import pytest

from fiscalberry.common.updater import appliers, commit_guard

EXE = "fiscalberry-gui.exe"


@pytest.fixture(autouse=True)
def estado_aislado(monkeypatch, tmp_path):
    monkeypatch.setattr(commit_guard, "_state_path",
                        lambda: str(tmp_path / "update_pending.json"))


@pytest.fixture
def rename_como_windows(monkeypatch):
    """os.rename con la regla de Windows: no se mueve la cwd de un proceso."""
    real = os.rename

    def rename(src, dst):
        cwd = os.path.normcase(os.path.abspath(os.getcwd()))
        origen = os.path.normcase(os.path.abspath(src))
        if cwd == origen or cwd.startswith(origen + os.sep):
            raise PermissionError(
                32, "El proceso no tiene acceso al archivo porque está siendo "
                    "utilizado por otro proceso", src)
        return real(src, dst)

    monkeypatch.setattr(appliers.os, "rename", rename)


@pytest.fixture
def ayudante_sin_esperas(monkeypatch):
    """El proceso viejo ya murió, sin sleeps, y se anotan los relanzamientos."""
    import time
    relanzados = []
    monkeypatch.setattr(appliers, "_proceso_vivo", lambda pid: False)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(appliers, "_relanzar", lambda b: relanzados.append(b))
    return relanzados


def _instalacion(carpeta, version):
    """Una carpeta onedir: el .exe y `_internal` al lado."""
    os.makedirs(os.path.join(carpeta, "_internal"))
    with open(os.path.join(carpeta, EXE), "w") as fh:
        fh.write(version)
    with open(os.path.join(carpeta, "_internal", "base_library.zip"), "w") as fh:
        fh.write(version)
    return str(carpeta)


def _version(carpeta):
    with open(os.path.join(carpeta, EXE)) as fh:
        return fh.read()


# --------------------------------------------------------------------------
# El bug
# --------------------------------------------------------------------------

def test_ayudante_con_la_cwd_en_la_instalacion_igual_la_reemplaza(
        tmp_path, monkeypatch, rename_como_windows, ayudante_sin_esperas):
    """
    El caso del local: el ayudante lo lanzó una versión <= 3.6.6, que no le
    fija la cwd, así que arranca parado en la carpeta a reemplazar. El ayudante
    nuevo tiene que salir de ahí solo.
    """
    dst = _instalacion(tmp_path / "fiscalberry-gui", "3.6.5")
    src = _instalacion(tmp_path / "tmp" / "nuevo", "3.6.7")
    monkeypatch.chdir(dst)

    codigo = appliers.run_apply_helper(pid=1234, src=src, dst=dst, exe=EXE)

    assert codigo == 0
    assert _version(dst) == "3.6.7"
    assert _version(dst + appliers.BACKUP_SUFFIX) == "3.6.5"
    assert ayudante_sin_esperas == [os.path.join(dst, EXE)]


def test_sin_salir_de_la_carpeta_falla_como_en_el_local_y_reabre_la_anterior(
        tmp_path, monkeypatch, rename_como_windows, ayudante_sin_esperas):
    """
    Reproduce el bug (el ayudante se queda con la cwd en la instalación) y fija
    lo mínimo que tiene que pasar si igual falla: volver a abrir la versión que
    estaba, en vez de dejar al local sin Fiscalberry.
    """
    dst = _instalacion(tmp_path / "fiscalberry-gui", "3.6.5")
    src = _instalacion(tmp_path / "tmp" / "nuevo", "3.6.7")
    monkeypatch.chdir(dst)
    monkeypatch.setattr(appliers, "_carpeta_neutral", lambda: dst)
    commit_guard.arm("3.6.7", "3.6.5", dst, dst + appliers.BACKUP_SUFFIX)

    codigo = appliers.run_apply_helper(pid=1234, src=src, dst=dst, exe=EXE)

    assert codigo == 1
    assert _version(dst) == "3.6.5"
    assert commit_guard.read() is None
    assert ayudante_sin_esperas == [os.path.join(dst, EXE)]


def test_apply_windows_no_le_pasa_su_cwd_al_ayudante(tmp_path, monkeypatch):
    dst = _instalacion(tmp_path / "fiscalberry-gui", "3.6.6")
    nuevo = _instalacion(tmp_path / "staging" / "fiscalberry-gui", "3.6.7")
    monkeypatch.chdir(dst)
    lanzados = []
    monkeypatch.setattr(appliers.subprocess, "Popen",
                        lambda args, **kw: lanzados.append((args, kw)))

    appliers.apply_windows(nuevo, dst, "3.6.7", "3.6.6", binario=EXE)

    (args, kw), = lanzados
    cwd = os.path.abspath(kw["cwd"])
    assert not (cwd == dst or cwd.startswith(dst + os.sep))


def test_relanzar_arranca_en_la_carpeta_del_programa(tmp_path, monkeypatch):
    """Igual que un acceso directo: la cwd del relanzado no es un temporal."""
    dst = _instalacion(tmp_path / "fiscalberry-gui", "3.6.7")
    lanzados = []
    monkeypatch.setattr(appliers.subprocess, "Popen",
                        lambda args, **kw: lanzados.append((args, kw)))

    appliers._relanzar(os.path.join(dst, EXE))

    (args, kw), = lanzados
    assert kw["cwd"] == dst


# --------------------------------------------------------------------------
# Nunca reemplazar una carpeta que tenga cosas del usuario
# --------------------------------------------------------------------------

def test_no_reemplaza_una_carpeta_con_archivos_ajenos(tmp_path, monkeypatch):
    """
    Si alguien dejó el .exe y `_internal` sueltos en Descargas, la "carpeta de
    instalación" es Descargas. Reemplazarla movería todo al respaldo, que se
    borra al confirmar. Se niega ANTES de cerrar el programa.
    """
    descargas = _instalacion(tmp_path / "Descargas", "3.6.6")
    (tmp_path / "Descargas" / "factura.pdf").write_text("del usuario")
    nuevo = _instalacion(tmp_path / "staging" / "fiscalberry-gui", "3.6.7")
    lanzados = []
    monkeypatch.setattr(appliers.subprocess, "Popen",
                        lambda args, **kw: lanzados.append((args, kw)))

    with pytest.raises(appliers.ApplyError, match="factura.pdf"):
        appliers.apply_windows(nuevo, descargas, "3.6.7", "3.6.6", binario=EXE)

    assert lanzados == []
    assert commit_guard.read() is None
    assert (tmp_path / "Descargas" / "factura.pdf").exists()


def test_el_ayudante_tampoco_reemplaza_una_carpeta_con_archivos_ajenos(
        tmp_path, ayudante_sin_esperas):
    """
    El ayudante es el binario NUEVO, pero quien decide actualizar es la versión
    vieja, que no hace este control. Por eso se repite acá.
    """
    descargas = _instalacion(tmp_path / "Descargas", "3.6.5")
    (tmp_path / "Descargas" / "factura.pdf").write_text("del usuario")
    src = _instalacion(tmp_path / "tmp" / "nuevo", "3.6.7")

    codigo = appliers.run_apply_helper(pid=1, src=src, dst=descargas, exe=EXE)

    assert codigo == 1
    assert (tmp_path / "Descargas" / "factura.pdf").exists()
    assert _version(descargas) == "3.6.5"
    assert not os.path.exists(descargas + appliers.BACKUP_SUFFIX)
    assert ayudante_sin_esperas == [os.path.join(descargas, EXE)]


def test_archivos_que_crea_windows_no_bloquean_la_actualizacion(tmp_path):
    dst = _instalacion(tmp_path / "fiscalberry-gui", "3.6.6")
    (tmp_path / "fiscalberry-gui" / "desktop.ini").write_text("")
    (tmp_path / "fiscalberry-gui" / "Thumbs.db").write_text("")
    nuevo = _instalacion(tmp_path / "staging" / "fiscalberry-gui", "3.6.7")

    appliers.verificar_destino(dst, nuevo, EXE)


def test_apply_posix_tampoco_reemplaza_una_carpeta_con_archivos_ajenos(tmp_path):
    home = _instalacion(tmp_path / "home", "3.6.6")
    (tmp_path / "home" / "notas.txt").write_text("del usuario")
    nuevo = _instalacion(tmp_path / "staging" / "fiscalberry-gui", "3.6.7")

    with pytest.raises(appliers.ApplyError):
        appliers.apply_posix(nuevo, home, "3.6.7", "3.6.6", binario=EXE)

    assert (tmp_path / "home" / "notas.txt").exists()
    assert _version(home) == "3.6.6"


# --------------------------------------------------------------------------
# Reversión automática en Windows
# --------------------------------------------------------------------------

def test_rollback_windows_corre_el_ayudante_desde_una_copia(tmp_path, monkeypatch):
    dst = _instalacion(tmp_path / "fiscalberry-gui", "3.6.7")
    backup = _instalacion(tmp_path / ("fiscalberry-gui" + appliers.BACKUP_SUFFIX),
                          "3.6.6")
    pend = commit_guard.arm("3.6.7", "3.6.6", dst, backup)
    monkeypatch.setattr(appliers, "_es_windows", lambda: True)
    lanzados = []
    monkeypatch.setattr(appliers.subprocess, "Popen",
                        lambda args, **kw: lanzados.append((args, kw)))

    assert appliers.rollback(pend) is True

    (args, kw), = lanzados
    src = args[args.index("--src") + 1]
    assert not appliers._mismo_camino(src, backup)
    assert _version(src) == "3.6.6"
    assert args[0] == os.path.join(src, EXE)
    assert not os.path.abspath(kw["cwd"]).startswith(dst)
    # Sin marca: la versión restaurada no tiene que volver a "revertir".
    assert commit_guard.read() is None


def test_ayudante_lanzado_desde_el_respaldo_no_lo_destruye(
        tmp_path, ayudante_sin_esperas):
    """
    Así lanzaba la reversión la versión <= 3.6.6: --src ES el respaldo. El
    ayudante lo borraba antes de usarlo y se quedaba sin la versión buena.
    """
    dst = _instalacion(tmp_path / "fiscalberry-gui", "3.6.7")
    backup = _instalacion(tmp_path / ("fiscalberry-gui" + appliers.BACKUP_SUFFIX),
                          "3.6.6")

    codigo = appliers.run_apply_helper(pid=1, src=backup, dst=dst, exe=EXE)

    assert codigo == 0
    assert _version(dst) == "3.6.6"
    assert _version(backup) == "3.6.6"
    assert _version(dst + appliers.DISCARD_SUFFIX) == "3.6.7"
