# coding=utf-8
"""
Descarga, verificación y desempaquetado.

Dos cosas se fijan acá:

1. Que un archivo que no coincide con su hash NUNCA se dé por bueno. Es la
   única defensa contra una descarga cortada o alterada.
2. Que un comprimido con rutas tipo '../../algo' no escriba fuera del staging.
   Es un agujero clásico de tarfile/zipfile, y acá el contenido viene de la red.
"""

import hashlib
import io
import os
import tarfile
import zipfile

import pytest

from fiscalberry.common.updater import staging


class FakeStreamResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._data), chunk_size):
            yield self._data[i:i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSession:
    def __init__(self, data):
        self._data = data

    def get(self, url, **kwargs):
        return FakeStreamResponse(self._data)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def test_descarga_con_hash_correcto(tmp_path):
    datos = b"contenido del binario" * 100
    destino = tmp_path / "asset.bin"

    staging.download("https://x/a", str(destino), _sha(datos),
                     session=FakeSession(datos))

    assert destino.read_bytes() == datos


def test_hash_que_no_coincide_aborta(tmp_path):
    datos = b"contenido alterado"
    destino = tmp_path / "asset.bin"

    with pytest.raises(staging.StagingError, match="checksum"):
        staging.download("https://x/a", str(destino), _sha(b"otra cosa"),
                         session=FakeSession(datos))


def test_sin_hash_esperado_ni_se_intenta(tmp_path):
    """No existe el modo 'bajalo igual y confiá'."""
    with pytest.raises(staging.StagingError):
        staging.download("https://x/a", str(tmp_path / "a"), "",
                         session=FakeSession(b"x"))


def test_tamano_distinto_al_publicado_aborta(tmp_path):
    datos = b"1234567890"
    with pytest.raises(staging.StagingError, match="tamaño"):
        staging.download("https://x/a", str(tmp_path / "a"), _sha(datos),
                         session=FakeSession(datos), expected_size=999)


def test_tar_con_ruta_que_se_escapa_es_rechazado(tmp_path):
    malicioso = tmp_path / "malo.tar.gz"
    with tarfile.open(malicioso, "w:gz") as tf:
        info = tarfile.TarInfo("../../fuera.txt")
        contenido = b"no deberia salir"
        info.size = len(contenido)
        tf.addfile(info, io.BytesIO(contenido))

    with pytest.raises(staging.StagingError, match="insegura"):
        staging.extract(str(malicioso), str(tmp_path / "destino"))

    assert not (tmp_path.parent / "fuera.txt").exists()


def test_zip_con_ruta_que_se_escapa_es_rechazado(tmp_path):
    malicioso = tmp_path / "malo.zip"
    with zipfile.ZipFile(malicioso, "w") as zf:
        zf.writestr("../../fuera.txt", "no deberia salir")

    with pytest.raises(staging.StagingError, match="insegura"):
        staging.extract(str(malicioso), str(tmp_path / "destino"))


def test_tar_con_symlink_es_rechazado(tmp_path):
    """Un symlink dentro del paquete puede apuntar a cualquier lado."""
    malicioso = tmp_path / "link.tar.gz"
    with tarfile.open(malicioso, "w:gz") as tf:
        info = tarfile.TarInfo("atajo")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tf.addfile(info)

    with pytest.raises(staging.StagingError, match="link"):
        staging.extract(str(malicioso), str(tmp_path / "destino"))


def test_extrae_y_encuentra_el_binario(tmp_path):
    binario = tmp_path / "fiscalberry-cli"
    binario.write_bytes(b"#!/bin/sh\necho hola\n")
    paquete = tmp_path / "ok.tar.gz"
    with tarfile.open(paquete, "w:gz") as tf:
        tf.add(str(binario), arcname="fiscalberry-cli")

    destino = staging.extract(str(paquete), str(tmp_path / "x"))
    encontrado = staging.find_binary(destino, "fiscalberry-cli")

    assert os.path.isfile(encontrado)


def test_binario_ausente_se_reporta_claro(tmp_path):
    paquete = tmp_path / "vacio.tar.gz"
    with tarfile.open(paquete, "w:gz") as tf:
        info = tarfile.TarInfo("otracosa")
        info.size = 0
        tf.addfile(info, io.BytesIO(b""))

    destino = staging.extract(str(paquete), str(tmp_path / "x"))
    with pytest.raises(staging.StagingError, match="fiscalberry-cli"):
        staging.find_binary(destino, "fiscalberry-cli")
