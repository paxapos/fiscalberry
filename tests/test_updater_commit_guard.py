# coding=utf-8
"""
Confirmación y reversión automática.

Lo que se fija acá es la propiedad que hace que esto sea seguro en un local:
si la versión nueva pasa el selftest pero NO logra levantar el servicio, a los
pocos arranques vuelve sola a la anterior. Sin esto, un binario que arranca y
muere deja al restaurante sin imprimir hasta que alguien vaya.
"""

import pytest

from fiscalberry.common.updater import commit_guard


@pytest.fixture(autouse=True)
def estado_aislado(monkeypatch, tmp_path):
    monkeypatch.setattr(commit_guard, "_state_path",
                        lambda: str(tmp_path / "update_pending.json"))


def _armar(tmp_path, version="3.5.0", previa="3.4.0"):
    destino = tmp_path / "fiscalberry-cli"
    destino.write_bytes(b"nuevo")
    backup = tmp_path / "fiscalberry-cli.fb-backup"
    backup.write_bytes(b"viejo")
    return commit_guard.arm(version, previa, str(destino), str(backup))


def test_sin_actualizacion_pendiente_no_hay_nada_que_hacer():
    pend, revertir = commit_guard.register_boot()
    assert pend is None
    assert revertir is False


def test_confirmar_borra_la_marca_y_el_respaldo(tmp_path):
    pend = _armar(tmp_path)
    assert commit_guard.read() is not None

    assert commit_guard.confirm() is True

    assert commit_guard.read() is None
    assert not tmp_path.joinpath("fiscalberry-cli.fb-backup").exists()


def test_un_arranque_confirmado_no_revierte(tmp_path):
    _armar(tmp_path)

    pend, revertir = commit_guard.register_boot()
    assert pend.boots == 1
    assert revertir is False

    commit_guard.confirm()
    assert commit_guard.read() is None


def test_revierte_recien_al_superar_el_tope(tmp_path):
    """
    MAX_BOOTS da margen para un reinicio ajeno (un corte de luz justo después
    de actualizar no debe hacernos volver atrás).
    """
    _armar(tmp_path)

    for esperado in range(1, commit_guard.MAX_BOOTS + 1):
        pend, revertir = commit_guard.register_boot()
        assert pend.boots == esperado
        assert revertir is False, f"revirtió demasiado pronto en el arranque {esperado}"

    pend, revertir = commit_guard.register_boot()
    assert revertir is True
    assert pend.previous_version == "3.4.0"


def test_el_contador_sobrevive_entre_procesos(tmp_path):
    """El estado va a disco justamente porque cada arranque es otro proceso."""
    _armar(tmp_path)
    commit_guard.register_boot()

    releido = commit_guard.read()
    assert releido.boots == 1
    assert releido.version == "3.5.0"


def test_marca_corrupta_se_descarta_sin_romper(tmp_path, monkeypatch):
    ruta = tmp_path / "update_pending.json"
    ruta.write_text("{esto no es json")

    assert commit_guard.read() is None
    # Y quedó limpia, para no repetir el error en cada arranque.
    assert not ruta.exists()


def test_confirmar_sin_pendiente_no_falla():
    assert commit_guard.confirm() is False
