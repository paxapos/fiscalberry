# coding=utf-8
"""
El config.ini se escribe de forma atómica.

Por qué importa: en Android el proceso de la UI y el del servicio comparten el
mismo config.ini. `open(path, 'w')` trunca el archivo al instante, así que
mientras se escribe queda vacío o a medias. Si el otro proceso lee justo en esa
ventana, encuentra un config SIN la sección SERVIDOR y concluye que hay que
resetearlo — y el dispositivo puede quedarse sin uuid.

Sin uuid, la pantalla de vinculación arma el link `<host>/adopt/` sin
identificador. El servidor responde 500 (`ArgumentCountError: Too few arguments
to adopt()`) y el QR queda en blanco. Pasó en producción.
"""

import os

import pytest

from fiscalberry.common.Configberry import Configberry


@pytest.fixture
def config(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    Configberry._instance = None
    c = Configberry()
    yield c
    Configberry._instance = None


def test_el_archivo_nunca_queda_truncado(config, monkeypatch):
    """
    Simula que la escritura explota a mitad de camino: el config previo tiene
    que sobrevivir intacto, no quedar vacío.
    """
    ruta = config.getConfigFIle()
    uuid_original = config.get("SERVIDOR", "uuid", fallback="")
    assert uuid_original, "el fixture deberia haber creado un uuid"

    original = open(ruta).read()

    real_replace = os.replace

    def replace_que_falla(src, dst):
        if str(dst) == str(ruta):
            raise OSError("disco lleno")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace_que_falla)
    config.set("SERVIDOR", {"sio_host": "https://otro.example.com"})

    # El archivo en disco quedó como estaba: ni vacío ni a medias.
    assert open(ruta).read() == original
    assert "[SERVIDOR]" in open(ruta).read()


def test_no_deja_temporales_tirados(config, monkeypatch):
    ruta = config.getConfigFIle()
    directorio = os.path.dirname(ruta)

    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda s, d: (_ for _ in ()).throw(OSError("no")))
    config.set("SERVIDOR", {"sio_host": "https://x.example.com"})
    monkeypatch.setattr(os, "replace", real_replace)

    sobrantes = [f for f in os.listdir(directorio) if f.endswith(".tmp")]
    assert sobrantes == [], f"quedaron temporales: {sobrantes}"


def test_una_escritura_normal_persiste(config):
    config.set("SERVIDOR", {"sio_host": "https://nuevo.example.com"})

    Configberry._instance = None
    otro = Configberry()
    assert otro.get("SERVIDOR", "sio_host") == "https://nuevo.example.com"
    # Y el uuid sigue siendo el mismo: cambiarlo obligaría a re-vincular.
    assert otro.get("SERVIDOR", "uuid", fallback="")


def test_el_uuid_sobrevive_a_muchas_escrituras(config):
    """El uuid es la identidad del equipo: ninguna escritura puede rotarlo."""
    uuid_original = config.get("SERVIDOR", "uuid")

    for i in range(10):
        config.set("SERVIDOR", {"sio_host": f"https://h{i}.example.com"})

    assert config.get("SERVIDOR", "uuid") == uuid_original
