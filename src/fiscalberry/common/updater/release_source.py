"""
De dónde sale "la versión que corresponde tener".

Se consulta `releases/latest` de GitHub, que devuelve el release más reciente
que NO sea borrador ni prerelease. Dos propiedades que el diseño aprovecha:

- Los prereleases quedan afuera solos, así que se pueden publicar builds de
  prueba sin que la flota los agarre.
- Si se borra un release, GitHub empieza a devolver el anterior. Por eso la
  regla es "tener lo que dice latest" y no "actualizar si hay algo más nuevo":
  borrar un release hace que la flota vuelva atrás sola.
"""

import json
import os
import re

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("Updater")

DEFAULT_REPO = "paxapos/fiscalberry"
API_URL = "https://api.github.com/repos/{repo}/releases/latest"
HTTP_TIMEOUT = 20

# Archivo de checksums que publica la CI junto a los binarios.
CHECKSUMS_ASSET = "SHA256SUMS"


class ReleaseUnavailable(Exception):
    """No se pudo averiguar cuál es el release vigente. No es un error fatal."""


def _version_tuple(version):
    """'3.4.10' -> (3, 4, 10). Solo para ordenar en los mensajes de log."""
    nums = re.findall(r"\d+", version or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def compare(a, b):
    """-1 si a<b, 0 si iguales, 1 si a>b. Para decir 'sube' o 'baja' en el log."""
    ta, tb = _version_tuple(a), _version_tuple(b)
    return (ta > tb) - (ta < tb)


class Release:
    def __init__(self, tag, version, assets):
        self.tag = tag
        self.version = version
        # {nombre: {"url": ..., "size": ...}}
        self.assets = assets

    def asset(self, name):
        return self.assets.get(name)

    def __repr__(self):
        return f"<Release {self.tag} assets={sorted(self.assets)}>"


def _etag_path():
    import platformdirs
    d = platformdirs.user_data_dir("fiscalberry")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "update_etag.json")


def _load_etag_cache():
    try:
        with open(_etag_path(), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_etag_cache(etag, payload):
    try:
        tmp = _etag_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"etag": etag, "payload": payload}, fh)
        os.replace(tmp, _etag_path())
    except Exception as e:
        logger.debug(f"No se pudo cachear el etag del release: {e}")


def fetch_latest(repo=DEFAULT_REPO, session=None):
    """
    Devuelve el Release vigente.

    Usa cabecera condicional (If-None-Match): un 304 no consume cuota de la API
    de GitHub, así que consultar seguido sale gratis. Con ~4 consultas por día
    por dispositivo estamos lejísimos del límite igual, pero la flota crece.
    """
    import requests

    sess = session or requests
    cache = _load_etag_cache()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if cache.get("etag"):
        headers["If-None-Match"] = cache["etag"]

    try:
        resp = sess.get(API_URL.format(repo=repo), headers=headers, timeout=HTTP_TIMEOUT)
    except Exception as e:
        raise ReleaseUnavailable(f"no se pudo consultar GitHub: {e}")

    if resp.status_code == 304 and cache.get("payload"):
        data = cache["payload"]
    elif resp.status_code == 200:
        data = resp.json()
        _save_etag_cache(resp.headers.get("ETag"), data)
    elif resp.status_code == 404:
        # Repo sin releases publicados todavía.
        raise ReleaseUnavailable("el repositorio no tiene releases")
    else:
        raise ReleaseUnavailable(f"GitHub respondió {resp.status_code}")

    tag = data.get("tag_name") or ""
    assets = {}
    for a in data.get("assets") or []:
        nombre = a.get("name")
        if nombre:
            assets[nombre] = {
                "url": a.get("browser_download_url"),
                "size": a.get("size"),
            }
    return Release(tag=tag, version=tag.lstrip("vV"), assets=assets)


def parse_checksums(texto):
    """
    Parsea un SHA256SUMS clásico ('<hash>  <archivo>' por línea).

    Devuelve {nombre_archivo: hash}. Ignora líneas que no tengan esa forma en
    vez de fallar: un archivo con una línea rara no debe bloquear todas las
    actualizaciones.
    """
    salida = {}
    for linea in (texto or "").splitlines():
        partes = linea.split()
        if len(partes) < 2:
            continue
        digest, nombre = partes[0], partes[-1]
        if len(digest) == 64 and all(c in "0123456789abcdefABCDEF" for c in digest):
            salida[os.path.basename(nombre.lstrip("*"))] = digest.lower()
    return salida


def fetch_checksums(release, session=None):
    """
    Descarga y parsea el SHA256SUMS del release.

    Si el release no lo trae, devuelve {} y el llamador debe ABORTAR: preferimos
    no actualizar antes que instalar un binario que no pudimos verificar.
    """
    import requests

    sess = session or requests
    asset = release.asset(CHECKSUMS_ASSET)
    if not asset:
        logger.warning(
            "El release %s no publica %s: no se puede verificar la descarga, "
            "se omite la actualizacion.", release.tag, CHECKSUMS_ASSET)
        return {}
    try:
        resp = sess.get(asset["url"], timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"No se pudo bajar {CHECKSUMS_ASSET}: {e}")
        return {}
    return parse_checksums(resp.text)
