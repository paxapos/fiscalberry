# coding=utf-8
"""
Primera apertura de la app: el config.ini tiene que salir COMPLETO.

Caso real (escritorio, primer arranque): el config.ini quedaba vacío y la
pantalla de vinculación terminaba regenerando solo el `uuid`, sin `sio_host`:

    WARNING GUI.AdoptScreen: No hay uuid en la configuración; se regenera.
    ERROR root: DISCOVER:: no hay 'sio_host' en el config ...
    ERROR GUI.App: UUID o sio_host no configurados

La causa era el ORDEN de importación: el arranque de la GUI importa primero
fiscalberry_logger, que construye un Configberry al importarse. Al crear el
config, Configberry importa device_uuid, que hacía
`from fiscalberry_logger import getLogger` sobre un módulo a medio cargar ->
ImportError, tragado por el try/except del logger. Y como Configberry ya se
había marcado como inicializado, nunca se volvía a intentar.

Se corre en un intérprete nuevo porque el problema depende de qué módulo se
importa primero, y dentro de pytest esos módulos ya están cargados.
"""

import configparser
import os
import subprocess
import sys

import pytest

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))


def _arrancar(tmp_path, codigo):
    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = str(tmp_path)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    resultado = subprocess.run(
        [sys.executable, "-c", codigo], env=env, cwd=str(tmp_path),
        capture_output=True, text=True, timeout=60,
    )
    assert resultado.returncode == 0, resultado.stderr
    en_disco = configparser.ConfigParser()
    en_disco.read(str(tmp_path / "Fiscalberry" / "config.ini"))
    return en_disco


@pytest.mark.skipif(sys.platform != "linux", reason="usa XDG_CONFIG_HOME")
@pytest.mark.parametrize("primero", [
    # Lo que hace desktop/main.py: el logger antes que nada.
    "import fiscalberry.common.fiscalberry_logger",
    "from fiscalberry.common.Configberry import Configberry",
])
def test_primer_arranque_crea_servidor_completo(tmp_path, primero):
    codigo = (
        f"{primero}\n"
        "from fiscalberry.common.Configberry import Configberry\n"
        "Configberry()\n"
    )
    en_disco = _arrancar(tmp_path, codigo)

    assert en_disco.has_section("SERVIDOR")
    assert en_disco.get("SERVIDOR", "uuid")
    assert en_disco.get("SERVIDOR", "sio_host").startswith("http")
