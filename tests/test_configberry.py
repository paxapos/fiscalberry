# coding=utf-8
"""
Tests baseline de Configberry.

Verifican el contrato público de `get(section, key, fallback=None)`:
  - lee valores existentes.
  - devuelve el fallback si no existe la clave.
  - refleja cambios escritos en el archivo.

Sirven de red de seguridad para la Fase 3 (cache por mtime): el comportamiento
observable de `get()` debe seguir siendo idéntico después de cachear.

Configberry es un singleton con un ConfigParser a nivel de clase. Para aislar el
test se apunta `configFilePath` a un INI temporal y se restaura el estado al final.
"""

import os

import pytest

from fiscalberry.common.Configberry import Configberry


def _bump_mtime(path):
    """Fuerza un mtime claramente mayor para no depender de la granularidad del FS."""
    future = os.path.getmtime(path) + 5
    os.utime(path, (future, future))


@pytest.fixture
def temp_config(tmp_path):
    cfg = Configberry()
    original_path = cfg.configFilePath
    ini = tmp_path / "config.ini"
    ini.write_text(
        "[SERVIDOR]\n"
        "verify_ssl = false\n"
        "\n"
        "[Paxaprinter]\n"
        "tenant = demo\n",
        encoding="utf-8",
    )
    cfg.configFilePath = str(ini)
    yield cfg, ini
    cfg.configFilePath = original_path


def test_get_returns_existing_value(temp_config):
    cfg, _ = temp_config
    assert cfg.get("Paxaprinter", "tenant") == "demo"
    assert cfg.get("SERVIDOR", "verify_ssl") == "false"


def test_get_returns_fallback_when_missing(temp_config):
    cfg, _ = temp_config
    assert cfg.get("SERVIDOR", "no_existe", fallback="default") == "default"
    assert cfg.get("SeccionInexistente", "clave", fallback=None) is None


def test_get_reflects_file_changes(temp_config):
    cfg, ini = temp_config
    assert cfg.get("Paxaprinter", "tenant") == "demo"

    # Cambiar el archivo en disco y asegurar que se refleje (mtime distinto).
    ini.write_text(
        "[SERVIDOR]\n"
        "verify_ssl = false\n"
        "\n"
        "[Paxaprinter]\n"
        "tenant = otro_comercio\n",
        encoding="utf-8",
    )
    _bump_mtime(str(ini))
    assert cfg.get("Paxaprinter", "tenant") == "otro_comercio"


def test_get_caches_and_reloads_on_mtime_change(temp_config, monkeypatch):
    """El cache evita releer el INI si no cambió; recarga si cambia el mtime."""
    cfg, ini = temp_config
    # Primera lectura: fuerza carga inicial y fija el mtime cacheado.
    assert cfg.get("Paxaprinter", "tenant") == "demo"

    # Espiar config.read para contar lecturas de disco.
    calls = {"n": 0}
    real_read = cfg.config.read

    def counting_read(*args, **kwargs):
        calls["n"] += 1
        return real_read(*args, **kwargs)

    monkeypatch.setattr(cfg.config, "read", counting_read)

    # Sin cambios en el archivo: no se relee del disco.
    for _ in range(5):
        cfg.get("Paxaprinter", "tenant")
    assert calls["n"] == 0

    # Cambia el archivo (mtime distinto): se relee exactamente una vez.
    ini.write_text("[Paxaprinter]\ntenant = nuevo\n", encoding="utf-8")
    _bump_mtime(str(ini))
    assert cfg.get("Paxaprinter", "tenant") == "nuevo"
    assert calls["n"] == 1
