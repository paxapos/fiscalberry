# coding=utf-8
"""
De dónde sale "la versión que corresponde tener".

El caso que más importa acá es el downgrade: la regla NO es "actualizar si hay
algo más nuevo" sino "tener exactamente lo que dice latest". Gracias a eso,
borrar un release malo hace que la flota entera vuelva sola a la anterior. Un
test que solo probara upgrades dejaría pasar una regresión que rompe justamente
el mecanismo de emergencia.
"""

import json

import pytest

from fiscalberry.common.updater import release_source


class FakeResponse:
    def __init__(self, status_code, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self._responses.pop(0)


def _release_payload(tag, assets):
    return {
        "tag_name": tag,
        "assets": [
            {"name": n, "browser_download_url": f"https://x/{n}", "size": 10}
            for n in assets
        ],
    }


@pytest.fixture(autouse=True)
def etag_aislado(monkeypatch, tmp_path):
    """El caché de etag vive en el data dir del usuario; se aísla por test."""
    monkeypatch.setattr(release_source, "_etag_path",
                        lambda: str(tmp_path / "etag.json"))


def test_parsea_el_tag_y_los_assets():
    sess = FakeSession([FakeResponse(200, _release_payload(
        "v3.5.0", ["fiscalberry-linux-cli.tar.gz", "SHA256SUMS"]))])

    rel = release_source.fetch_latest("paxapos/fiscalberry", session=sess)

    assert rel.version == "3.5.0"
    assert rel.tag == "v3.5.0"
    assert rel.asset("SHA256SUMS")["url"] == "https://x/SHA256SUMS"


def test_repo_sin_releases_no_es_un_crash():
    sess = FakeSession([FakeResponse(404)])

    with pytest.raises(release_source.ReleaseUnavailable):
        release_source.fetch_latest("paxapos/fiscalberry", session=sess)


def test_304_reusa_el_payload_cacheado(tmp_path, monkeypatch):
    """Un 304 no consume cuota de la API; hay que servir del caché."""
    payload = _release_payload("v3.5.0", ["SHA256SUMS"])
    ruta = tmp_path / "etag.json"
    ruta.write_text(json.dumps({"etag": 'W/"abc"', "payload": payload}))
    monkeypatch.setattr(release_source, "_etag_path", lambda: str(ruta))

    sess = FakeSession([FakeResponse(304)])
    rel = release_source.fetch_latest("paxapos/fiscalberry", session=sess)

    assert rel.version == "3.5.0"
    # Y mandó la cabecera condicional.
    assert sess.requests[0][1]["headers"]["If-None-Match"] == 'W/"abc"'


def test_compare_detecta_que_latest_es_menor():
    """El caso del botón de pánico: se borró un release y latest bajó."""
    assert release_source.compare("3.4.0", "3.5.0") == -1
    assert release_source.compare("3.5.0", "3.4.0") == 1
    assert release_source.compare("3.5.0", "3.5.0") == 0


def test_compare_ordena_numericamente_no_alfabeticamente():
    """'3.10.0' es mayor que '3.9.0' aunque como texto sea al revés."""
    assert release_source.compare("3.10.0", "3.9.0") == 1


def test_parse_checksums_formato_sha256sum():
    texto = (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  "
        "fiscalberry-linux-cli.tar.gz\n"
        "d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2 *"
        "fiscalberry-windows-cli.zip\n"
    )
    sums = release_source.parse_checksums(texto)

    assert sums["fiscalberry-linux-cli.tar.gz"].startswith("e3b0c442")
    # El '*' del formato binario no debe quedar pegado al nombre.
    assert "fiscalberry-windows-cli.zip" in sums


def test_parse_checksums_ignora_basura_sin_romper():
    """Una línea rara no puede dejar a la flota sin poder actualizarse."""
    texto = "esto no es un hash\n" + "a" * 64 + "  archivo.zip\n"
    sums = release_source.parse_checksums(texto)
    assert sums == {"archivo.zip": "a" * 64}


def test_sin_sha256sums_devuelve_vacio():
    """Sin checksums el updater debe abstenerse, no adivinar."""
    rel = release_source.Release("v3.5.0", "3.5.0", {})
    assert release_source.fetch_checksums(rel, session=FakeSession([])) == {}
