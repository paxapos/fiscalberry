# coding=utf-8
"""
Actualización de una instalación desde código (pip).

Igual que los binarios: el tarball del release se baja, se verifica contra el
SHA256SUMS del release y recién ahí pip instala el archivo LOCAL. Sin checksum,
o con uno que no coincide, no se instala nada. Sin red: las descargas salen de
un diccionario url -> bytes.
"""

import hashlib
import logging
import os

import pytest
import requests

from fiscalberry.common.updater import (
    appliers,
    install_kind,
    release_source,
    service,
)
from fiscalberry.version import VERSION

TARBALL = "fiscalberry-source.tar.gz"
NUEVO = b"codigo de la version nueva" * 50
PREVIO = b"codigo de la version que corre" * 50


def _sha(datos):
    return hashlib.sha256(datos).hexdigest()


def _sums(**hashes):
    return "".join(f"{h}  {nombre}\n" for nombre, h in hashes.items()).encode()


class _Respuesta:
    def __init__(self, datos):
        self._datos = datos
        self.status_code = 200 if datos is not None else 404

    @property
    def text(self):
        return self._datos.decode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._datos), chunk_size):
            yield self._datos[i:i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def red(monkeypatch):
    """url -> bytes. Lo que no está da 404: ningún test sale a internet."""
    publicado = {}
    monkeypatch.setattr(requests, "get",
                        lambda url, **kw: _Respuesta(publicado.get(url)))
    return publicado


@pytest.fixture
def instalaciones(monkeypatch):
    """Instalación desde código, cola vacía; anota qué recibió pip."""
    pip = []

    def fake_pip(origen):
        contenido = None
        if os.path.isfile(origen):
            with open(origen, "rb") as fh:
                contenido = fh.read()
        pip.append((origen, contenido))
        return True

    monkeypatch.setattr(install_kind, "detect", lambda: install_kind.SOURCE)
    monkeypatch.setattr(service, "spooler_idle", lambda: True)
    monkeypatch.setattr(appliers, "_pip_install", fake_pip)
    monkeypatch.setattr(appliers, "_selftest_modulo", lambda v: (True, "ok"))
    monkeypatch.setattr(service.UpdaterService, "_pedir_reinicio", lambda self: None)
    return pip


def _publicar(monkeypatch, red, tarball=NUEVO, sums=None, con_sums=True):
    base = "https://x/v99.0.0/"
    assets = {TARBALL: {"url": base + TARBALL, "size": None}}
    red[base + TARBALL] = tarball
    if con_sums:
        assets[release_source.CHECKSUMS_ASSET] = {
            "url": base + release_source.CHECKSUMS_ASSET, "size": None}
        red[base + release_source.CHECKSUMS_ASSET] = (
            sums if sums is not None else _sums(**{TARBALL: _sha(tarball)}))
    rel = release_source.Release("v99.0.0", "99.0.0", assets)
    monkeypatch.setattr(release_source, "fetch_latest",
                        lambda repo=None, session=None: rel)


def _publicar_previo(red, tarball=PREVIO):
    """El release de la versión que corre, por tag (descarga directa)."""
    def url(nombre):
        return release_source.DOWNLOAD_URL.format(
            repo=release_source.DEFAULT_REPO, tag=f"v{VERSION}", name=nombre)
    red[url(TARBALL)] = tarball
    red[url(release_source.CHECKSUMS_ASSET)] = _sums(**{TARBALL: _sha(tarball)})


def test_tarball_verificado_se_instala_desde_el_archivo_local(monkeypatch, red, instalaciones):
    _publicar(monkeypatch, red)

    estado, detalle = service.UpdaterService().check_once()

    assert (estado, detalle) == ("aplicado", "99.0.0")
    assert len(instalaciones) == 1
    origen, contenido = instalaciones[0]
    assert not origen.startswith(("http://", "https://")), origen
    assert contenido == NUEVO


def test_checksum_que_no_coincide_no_instala(monkeypatch, red, instalaciones, caplog):
    _publicar(monkeypatch, red, sums=_sums(**{TARBALL: _sha(b"otra cosa")}))

    with caplog.at_level(logging.ERROR, logger="Updater"):
        estado, _ = service.UpdaterService().check_once()

    assert estado == "descartado"
    assert instalaciones == []
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_release_sin_sha256sums_no_instala(monkeypatch, red, instalaciones, caplog):
    _publicar(monkeypatch, red, con_sums=False)

    with caplog.at_level(logging.ERROR, logger="Updater"):
        estado, _ = service.UpdaterService().check_once()

    assert estado == "sin-checksums"
    assert instalaciones == []
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_sha256sums_sin_la_linea_del_tarball_no_instala(monkeypatch, red, instalaciones):
    _publicar(monkeypatch, red, sums=_sums(**{"fiscalberry-linux-cli.tar.gz": "0" * 64}))

    estado, _ = service.UpdaterService().check_once()

    assert estado == "sin-checksums"
    assert instalaciones == []


def test_si_la_nueva_no_pasa_el_selftest_vuelve_al_tarball_verificado_de_la_anterior(
        monkeypatch, red, instalaciones):
    _publicar(monkeypatch, red)
    _publicar_previo(red)
    monkeypatch.setattr(appliers, "_selftest_modulo", lambda v: (False, "roto"))

    estado, _ = service.UpdaterService().check_once()

    assert estado == "error"
    assert [contenido for _, contenido in instalaciones] == [NUEVO, PREVIO]
    assert not any(o.startswith(("http://", "https://")) for o, _ in instalaciones)


def test_sin_tarball_verificado_de_la_anterior_no_revierte_sin_verificar(
        monkeypatch, red, instalaciones):
    _publicar(monkeypatch, red)
    monkeypatch.setattr(appliers, "_selftest_modulo", lambda v: (False, "roto"))

    estado, _ = service.UpdaterService().check_once()

    assert estado == "error"
    assert [contenido for _, contenido in instalaciones] == [NUEVO]
