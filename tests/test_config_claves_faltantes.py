# coding=utf-8
"""
Un config al que le falta una clave tiene que repararse solo.

Caso real, diagnosticado con el log de un celular: el `config.ini` tenía `uuid`
pero **no** `sio_host`. Y el chequeo de integridad solo exigía que existiera
`uuid`, así que ese config se consideraba válido para siempre; `sio_host` solo
se escribe en el reset, que en ese estado ya no se dispara nunca.

Consecuencias en el dispositivo:

    ERROR ServiceController: sio_host no configurado
    ERROR GUI.App: UUID o sio_host no configurados

Sin `sio_host` no salía NADA de red —ni el discover ni SocketIO—, así que el
servidor nunca supo que el dispositivo existía y la vinculación moría con
":: Paxaprinter no encontrada".
"""

import configparser

import pytest

from fiscalberry.common.Configberry import Configberry


@pytest.fixture
def config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    Configberry._instance = None
    yield tmp_path / "Fiscalberry"
    Configberry._instance = None


def _escribir_config(directorio, contenido):
    directorio.mkdir(parents=True, exist_ok=True)
    (directorio / "config.ini").write_text(contenido)


def test_completa_sio_host_si_falta(config_dir):
    """El caso exacto del celular: uuid presente, sio_host ausente."""
    _escribir_config(config_dir, "[SERVIDOR]\nuuid = 009ee616-c2ad-592c-955d-2d2fb1118f4a\n")

    cfg = Configberry()

    assert cfg.get("SERVIDOR", "sio_host")
    assert cfg.get("SERVIDOR", "sio_host").startswith("http")


def test_no_pisa_el_uuid_al_completar(config_dir):
    """El uuid es la identidad del equipo: reparar el config no puede rotarlo."""
    _escribir_config(config_dir, "[SERVIDOR]\nuuid = 009ee616-c2ad-592c-955d-2d2fb1118f4a\n")

    cfg = Configberry()

    assert cfg.get("SERVIDOR", "uuid") == "009ee616-c2ad-592c-955d-2d2fb1118f4a"


def test_respeta_un_host_ya_configurado(config_dir):
    """Si alguien apuntó el equipo a otro servidor, no se lo cambiamos."""
    _escribir_config(config_dir,
                     "[SERVIDOR]\nuuid = abc-123\n"
                     "sio_host = https://dev2.paxapos.com\n")

    cfg = Configberry()

    assert cfg.get("SERVIDOR", "sio_host") == "https://dev2.paxapos.com"


def test_la_reparacion_queda_en_disco(config_dir):
    """Si no persiste, el problema vuelve en el próximo arranque."""
    _escribir_config(config_dir, "[SERVIDOR]\nuuid = abc-123\n")

    Configberry()

    en_disco = configparser.ConfigParser()
    en_disco.read(str(config_dir / "config.ini"))
    assert en_disco.get("SERVIDOR", "sio_host").startswith("http")


def test_completa_todas_las_claves_necesarias(config_dir):
    _escribir_config(config_dir, "[SERVIDOR]\nuuid = abc-123\n")

    cfg = Configberry()

    for clave in Configberry.SERVIDOR_DEFAULTS:
        assert cfg.get("SERVIDOR", clave) is not None, f"falta {clave}"


def test_no_toca_las_secciones_de_impresoras(config_dir):
    _escribir_config(config_dir,
                     "[SERVIDOR]\nuuid = abc-123\n\n"
                     "[Cocina]\ndriver = Network\nhost = 192.168.1.50\n")

    cfg = Configberry()

    assert cfg.get("Cocina", "host") == "192.168.1.50"
    assert cfg.get("Cocina", "driver") == "Network"
