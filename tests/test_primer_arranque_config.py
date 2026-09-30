# coding=utf-8
"""
Primer arranque en un equipo recién instalado, sin config.ini.

desktop/main.py (y el selftest) importan primero fiscalberry_logger, que crea
el Configberry al importarse; el Configberry, al no encontrar config.ini, lo
resetea e importa device_uuid. Si device_uuid importaba el logger de
fiscalberry_logger, el círculo fallaba a mitad de camino: el config.ini
quedaba vacío y ese proceso arrancaba sin uuid ni sio_host. Lo destapó la
prueba del instalador en CI (#187): la app relanzada tras instalar decía
"sio_host no configurado".
"""

import configparser
import os
import subprocess
import sys
import textwrap

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))


def test_el_primer_arranque_deja_un_config_ini_completo(tmp_path):
    codigo = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {SRC!r})
        # El mismo orden que desktop/main.py y el modo --selftest.
        import fiscalberry.common.fiscalberry_logger  # noqa: F401
        from fiscalberry.common.Configberry import Configberry
        print("SIO_HOST=" + str(Configberry().get("SERVIDOR", "sio_host")))
    """)
    entorno = dict(os.environ)
    entorno["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    entorno["XDG_DATA_HOME"] = str(tmp_path / "data")

    proc = subprocess.run([sys.executable, "-c", codigo], capture_output=True,
                          text=True, timeout=120, env=entorno)

    assert "SIO_HOST=https://" in proc.stdout, proc.stdout + proc.stderr
    ruta = tmp_path / "config" / "Fiscalberry" / "config.ini"
    config = configparser.ConfigParser()
    config.read(ruta)
    assert config.get("SERVIDOR", "uuid", fallback=""), ruta.read_text()
    assert config.get("SERVIDOR", "sio_host", fallback="").startswith("https://")
