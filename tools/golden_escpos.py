# -*- coding: utf-8 -*-
"""
Goldens de bytes ESC/POS: lo que EscPComandos manda HOY a la impresora.

Para cada payload de ``tests/golden/payloads/*.json`` corre ``EscPComandos.run()``
con el driver ``Dummy`` de python-escpos y guarda los bytes exactos en
``tests/golden/bytes/<nombre>.<cols>.bin``, uno por ancho de papel (40 y 32).

Esos archivos son la verdad contra la que Paxapos prueba que su render server-side
(``Plugin/Printers/Utility/EscPos/``) sale byte a byte igual (épica
paxapos/paxapos#1723, S1 / S2). Además se exportan dos referencias que Paxapos
necesita para reproducir python-escpos sin Python:

- ``tests/golden/codepages.json``: los caracteres 128-255 de cada codepage, tal
  como los ve el MagicEncode de python-escpos.
- ``tests/golden/qr.json``: la matriz de módulos de cada QR que aparece en los
  payloads (python-qrcode), para aislar un QR distinto de un ticket distinto.

La hora se congela en ``FROZEN_NOW``: los comprobantes que imprimen
``datetime.now()`` (pedido, remito con fecha, pie de factura y de arqueo) salen
siempre iguales. ``%x`` se resuelve con locale C, como en los dispositivos.

Uso:
    python tools/golden_escpos.py            # regenera todo (después de cambiar un formato a propósito)
    python tools/golden_escpos.py --check    # falla si EscPComandos imprime distinto que los goldens

Un cambio en EscPComandos que cambie un byte rompe ``--check`` (y el test
``tests/test_golden_escpos.py``): o es un bug, o es un cambio de formato que
también hay que hacer en Paxapos (y entonces se regeneran los goldens acá).
"""

import argparse
import datetime as _datetime_real
import json
import locale
import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def _aislar_config_del_usuario():
    """Importar fiscalberry crea su config.ini: que sea en un directorio temporal."""
    import atexit
    import shutil
    import tempfile

    base = tempfile.mkdtemp(prefix="fiscalberry-goldens-")
    atexit.register(shutil.rmtree, base, ignore_errors=True)
    for var, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
        os.environ.setdefault(var, os.path.join(base, sub))

GOLDEN_DIR = os.path.join(ROOT, "tests", "golden")
PAYLOADS_DIR = os.path.join(GOLDEN_DIR, "payloads")
BYTES_DIR = os.path.join(GOLDEN_DIR, "bytes")
CODEPAGES_FILE = os.path.join(GOLDEN_DIR, "codepages.json")
QR_FILE = os.path.join(GOLDEN_DIR, "qr.json")
META_FILE = os.path.join(GOLDEN_DIR, "meta.json")

COLUMNS = (40, 32)
FROZEN_NOW = _datetime_real.datetime(2026, 7, 10, 21, 45, 0)

# Versiones con las que se generaron los goldens: el texto lo encodea
# python-escpos y el QR lo arma qrcode; con otras versiones los bytes pueden
# cambiar sin que EscPComandos haya cambiado. Pillow solo convierte una imagen
# en blanco y negro puro (no cambia los bytes) y no se fija: Kivy pide pillow<11.
PINNED = ("python-escpos", "qrcode")


def _version(dist):
    try:
        from importlib.metadata import version
        return version(dist)
    except Exception:
        return None


def versions():
    from fiscalberry.version import VERSION
    data = {dist: _version(dist) for dist in PINNED + ("pillow",)}
    data["fiscalberry"] = VERSION
    return data


class _FrozenDatetime(_datetime_real.datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW


def _frozen_datetime_module():
    module = types.ModuleType("datetime")
    for name in dir(_datetime_real):
        if not name.startswith("__"):
            setattr(module, name, getattr(_datetime_real, name))
    module.datetime = _FrozenDatetime
    return module


def _freeze(escp_module):
    escp_module.datetime = _frozen_datetime_module()
    try:
        locale.setlocale(locale.LC_TIME, "C")
    except locale.Error:
        pass


def payload_names():
    return sorted(f[:-5] for f in os.listdir(PAYLOADS_DIR) if f.endswith(".json"))


def load_payload(name):
    with open(os.path.join(PAYLOADS_DIR, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def render(payload, columns):
    """Bytes que EscPComandos manda a la impresora para este payload."""
    from escpos.printer import Dummy
    import fiscalberry.common.EscPComandos as escp_module

    _freeze(escp_module)
    printer = Dummy()
    resultado = escp_module.EscPComandos(printer, columns=columns).run(json.loads(json.dumps(payload)))
    for accion in resultado:
        rta = accion.get("rta")
        if isinstance(rta, str) and rta.startswith(("Error", "Function not found")):
            raise RuntimeError(f"{accion['action']}: {rta}")
    return printer.output


def export_codepages():
    """Caracteres 128-255 de cada codepage, como los resuelve el MagicEncode."""
    from escpos.capabilities import CAPABILITIES
    from escpos.magicencode import Encoder

    tablas = {}
    for nombre in sorted(CAPABILITIES["encodings"]):
        try:
            chars = Encoder._get_codepage_char_list(nombre)
        except (LookupError, KeyError, AssertionError):
            continue
        tablas[nombre] = "".join(chars)
    return tablas


def _qr_contents(payload):
    """Textos de QR que imprime el payload (el de AFIP se arma igual que EscPComandos)."""
    contenidos = []
    for accion, params in payload.items():
        if not isinstance(params, dict):
            continue
        for clave in ("qr", "qr-mercadopago"):
            if params.get(clave):
                contenidos.append((clave, params[clave], "L", 5))
        if accion == "printFacturaElectronica":
            contenidos.append(("afip", _afip_qr_url(params), "H", 3))
    return contenidos


def _afip_qr_url(params):
    """Mismo armado que EscPComandos.printFacturaElectronica (sección 8)."""
    import base64
    from fiscalberry.common.EscPComandos import to_float

    enc = params["encabezado"]
    fecha_cmp = enc.get("fecha_comprobante")
    felist = fecha_cmp.split("/") if "/" in fecha_cmp else fecha_cmp.split("-")
    numlist = enc.get("numero_comprobante").split("-")
    ctz = to_float(enc.get("ctz", 1))
    ctz_qr = ctz if ctz > 0 else 1
    if isinstance(ctz_qr, float) and ctz_qr.is_integer():
        ctz_qr = int(ctz_qr)
    qr = {
        "ver": 1, "fecha": felist[2] + "-" + felist[1] + "-" + felist[0],
        "cuit": int(enc.get("cuit_empresa")), "ptoVta": int(numlist[0]),
        "tipoCmp": int(enc.get("tipo_comprobante_codigo")), "nroCmp": int(numlist[1]),
        "importe": float(enc.get("importe_total")), "moneda": enc.get("moneda") or "PES", "ctz": ctz_qr,
    }
    if enc.get("tipoDocRec") and enc.get("documento_cliente"):
        qr["tipoDocRec"] = int(enc.get("tipoDocRec"))
        qr["nroDocRec"] = int(enc.get("documento_cliente"))
    qr["tipoCodAut"] = "E"
    qr["codAut"] = int(enc.get("cae"))
    data = base64.encodebytes(json.dumps(qr).encode()).decode().replace("\n", "")
    return "https://www.afip.gob.ar/fe/qr/?p=" + data


def export_qr():
    """Matriz de módulos (python-qrcode, border=1 como python-escpos) de cada QR de los payloads."""
    import qrcode

    niveles = {"L": qrcode.constants.ERROR_CORRECT_L, "H": qrcode.constants.ERROR_CORRECT_H}
    salida = {}
    for name in payload_names():
        for clave, contenido, nivel, size in _qr_contents(load_payload(name)):
            qr = qrcode.QRCode(version=None, box_size=size, border=1, error_correction=niveles[nivel])
            qr.add_data(contenido)
            qr.make(fit=True)
            modulos = ["".join("1" if m else "0" for m in fila) for fila in qr.modules]
            # best_mask_pattern() rearma la matriz: se llama después de copiarla.
            salida[f"{name}:{clave}"] = {
                "content": contenido,
                "ec": nivel,
                "box_size": size,
                "version": qr.version,
                "mask": qr.best_mask_pattern(),
                "modules": modulos,
            }
    return salida


def build():
    """Todo lo que se versiona, como {ruta: bytes}."""
    archivos = {}
    for name in payload_names():
        payload = load_payload(name)
        for cols in COLUMNS:
            archivos[os.path.join(BYTES_DIR, f"{name}.{cols}.bin")] = render(payload, cols)
    archivos[CODEPAGES_FILE] = _json_bytes(export_codepages())
    archivos[QR_FILE] = _json_bytes(export_qr())
    archivos[META_FILE] = _json_bytes({
        "generator": "tools/golden_escpos.py",
        "frozen_now": FROZEN_NOW.strftime("%Y-%m-%d %H:%M:%S"),
        "locale_time": "C",
        "columns": list(COLUMNS),
        "driver": "escpos.printer.Dummy (perfil default)",
        "versions": versions(),
    })
    return archivos


def _json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def check(archivos):
    """Lista de diferencias entre lo que se generaría y lo versionado."""
    diferencias = []
    esperados = set(archivos)
    for ruta, contenido in sorted(archivos.items()):
        if ruta == META_FILE:
            # Las versiones que importan las valida version_mismatch(); el resto
            # (Pillow, fiscalberry) es informativo.
            continue
        rel = os.path.relpath(ruta, ROOT)
        if not os.path.exists(ruta):
            diferencias.append(f"falta {rel}")
            continue
        with open(ruta, "rb") as f:
            actual = f.read()
        if actual != contenido:
            diferencias.append(f"distinto {rel}{_primer_offset(actual, contenido)}")
    if os.path.isdir(BYTES_DIR):
        for f in sorted(os.listdir(BYTES_DIR)):
            ruta = os.path.join(BYTES_DIR, f)
            if ruta not in esperados:
                diferencias.append(f"sobra {os.path.relpath(ruta, ROOT)} (no tiene payload)")
    return diferencias


def _primer_offset(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f" (primer byte distinto en el offset {i})"
    return f" (largo {len(a)} vs {len(b)})"


def version_mismatch():
    """Versiones instaladas que no coinciden con las de meta.json (None si coinciden)."""
    if not os.path.exists(META_FILE):
        return None
    with open(META_FILE, encoding="utf-8") as f:
        esperadas = json.load(f).get("versions", {})
    distintas = {d: (esperadas.get(d), v) for d, v in versions().items() if d in PINNED and esperadas.get(d) != v}
    return distintas or None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="no escribe: falla si algo cambió")
    args = parser.parse_args(argv)

    archivos = build()
    if args.check:
        distintas = version_mismatch()
        if distintas:
            print("Versiones distintas a las de los goldens (instalá requirements.dev.txt):")
            for dist, (esperada, actual) in distintas.items():
                print(f"  {dist}: goldens {esperada}, instalada {actual}")
            return 2
        diferencias = check(archivos)
        if diferencias:
            print("EscPComandos ya no imprime lo mismo que los goldens:")
            for d in diferencias:
                print("  " + d)
            print("Si el cambio de formato es a propósito: python tools/golden_escpos.py (y replicarlo en Paxapos).")
            return 1
        print(f"OK: {len(archivos)} archivos idénticos a los goldens.")
        return 0

    os.makedirs(BYTES_DIR, exist_ok=True)
    for f in os.listdir(BYTES_DIR):
        if os.path.join(BYTES_DIR, f) not in archivos:
            os.remove(os.path.join(BYTES_DIR, f))
    for ruta, contenido in archivos.items():
        with open(ruta, "wb") as f:
            f.write(contenido)
    print(f"Escritos {len(archivos)} archivos en {os.path.relpath(GOLDEN_DIR, ROOT)}/")
    return 0


if __name__ == "__main__":
    _aislar_config_del_usuario()
    sys.exit(main())
