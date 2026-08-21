#!/usr/bin/env python3
"""
p4a hook: fija el target API del dist e inyecta android:foregroundServiceType.

Dos parches, en dos momentos distintos del build:

1. before_apk_build → project.properties. p4a lee de ahí el target API para
   renderizar build.gradle (compileSdkVersion/targetSdkVersion), pero ese
   archivo se escribe UNA sola vez, al crear el dist. Con un dist cacheado de
   un build viejo, subir android.api en el .spec no tiene ningún efecto y el
   APK sale con el target anterior (Play Protect bloquea la instalación:
   "diseñada para una versión anterior de Android"). La CI es vulnerable a lo
   mismo por sus restore-keys de caché. Acá lo forzamos a ctx.android_api.

2. after_apk_build → AndroidManifest.xml (ver detalle abajo).

El foregroundServiceType es obligatorio desde Android 14 (API 34+): un service sin type
declarado hace que startForeground() lance MissingForegroundServiceTypeException
y el servicio muera al arrancar. p4a v2024.01.21 no soporta declararlo
(su template renderiza el <service> sin ese atributo), de ahí este hook.

TIMING: se engancha en after_apk_build / before_apk_assemble, NO en
before_apk_build. p4a genera el manifest dentro de
build.parse_args_and_make_package(), que corre DESPUÉS de before_apk_build:
parchear ahí no encuentra el archivo (o lo pisa la generación posterior).
Durante el hook el cwd es el dist_dir, así que de ahí salen los candidatos.
"""

import os
import re
from pathlib import Path

# SOLO connectedDevice, a propósito: en Android 15 (API 35) un FGS de tipo
# dataSync está limitado a 6 horas por cada 24 — el sistema llama onTimeout() y
# frena el servicio (y p4a no implementa onTimeout). Para un servicio de
# impresión 24/7 eso significa morirse solo todos los días. connectedDevice no
# tiene ese límite y describe bien lo que hace: hablar con impresoras
# (red/USB/Bluetooth). Sus prerequisitos de permisos los cubren
# CHANGE_WIFI_STATE / CHANGE_NETWORK_STATE, que son normales (se conceden al
# instalar, sin diálogo), así que no dependemos de que el usuario acepte nada.
FOREGROUND_TYPES = "connectedDevice"

# El <service> lo genera buildozer a partir de `services =` del .spec.
SERVICE_PATTERN = r'(<service[^>]*android:name="[^"]*[Ss]ervice[Ff]iscalberry[^"]*"[^>]*?)(\s*/?>)'


def _candidate_manifests(toolchain):
    """Manifests a parchear: el que consume gradle (src/main) y el del dist."""
    dist_dirs = []

    # Durante el hook, p4a hace chdir al dist_dir.
    dist_dirs.append(Path.cwd())

    for attr in ("dist_dir",):
        for obj in (toolchain, getattr(toolchain, "ctx", None)):
            value = getattr(obj, attr, None) if obj is not None else None
            if value:
                dist_dirs.append(Path(value))

    candidates = []
    for dist_dir in dist_dirs:
        for rel in ("src/main/AndroidManifest.xml", "AndroidManifest.xml"):
            candidates.append(dist_dir / rel)
        # ctx.dist_dir puede apuntar al padre 'dists/': buscar un nivel abajo.
        candidates.extend(dist_dir.glob("*/src/main/AndroidManifest.xml"))
        candidates.extend(dist_dir.glob("*/AndroidManifest.xml"))

    seen = set()
    unique = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen and resolved.exists():
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _patch_manifest(manifest_path):
    content = manifest_path.read_text(encoding="utf-8")

    if "android:foregroundServiceType" in content:
        print(f"[p4a_hook] foregroundServiceType ya presente en {manifest_path}")
        return True

    new_content, count = re.subn(
        SERVICE_PATTERN,
        r'\1 android:foregroundServiceType="%s"\2' % FOREGROUND_TYPES,
        content,
    )

    if not count:
        print(f"[p4a_hook] ⚠ No se encontró el service de Fiscalberry en {manifest_path}")
        for svc in re.findall(r"<service[^>]*>", content):
            print(f"[p4a_hook]   - {svc[:120]}")
        return False

    manifest_path.write_text(new_content, encoding="utf-8")
    print(f"[p4a_hook] ✓ foregroundServiceType agregado en {manifest_path} ({count} service/s)")
    return True


def before_apk_build(toolchain):
    """
    Corre ANTES de que p4a genere build.gradle: acá forzamos el target API real
    en project.properties, del que p4a lo lee. Sin esto, un dist cacheado deja
    el target viejo aunque android.api del .spec haya subido.
    """
    android_api = _android_api(toolchain)

    if not android_api:
        raise RuntimeError(
            "[p4a_hook] No se pudo determinar android_api del toolchain: el APK "
            "saldría con el target del dist cacheado, sin aviso."
        )

    expected = f"target=android-{android_api}"

    for props in {Path.cwd() / "project.properties", *Path.cwd().glob("*/project.properties")}:
        if not props.exists():
            continue
        current = props.read_text(encoding="utf-8").strip()
        if current == expected:
            print(f"[p4a_hook] project.properties ya en {expected} ({props})")
            continue
        props.write_text(expected + "\n", encoding="utf-8")
        print(f"[p4a_hook] ✓ project.properties: '{current}' → '{expected}' ({props})")


def _android_api(toolchain):
    ctx = getattr(toolchain, "ctx", None)
    return getattr(ctx, "android_api", None) if ctx is not None else None


def after_apk_build(toolchain):
    """
    Corre después de generar el manifest y antes de que gradle ensamble el APK.

    Si no se pudo parchear y el target es API 34+, ABORTA el build: un APK sin
    foregroundServiceType compila perfecto pero el servicio muere al arrancar
    (MissingForegroundServiceTypeException, en Java, antes de cualquier línea de
    Python). Un warning impreso a mitad de un build de 40 minutos no lo ve
    nadie, y el release se publicaría igual.
    """
    manifests = _candidate_manifests(toolchain)
    patched = [m for m in manifests if _patch_manifest(m)]

    if patched:
        return

    android_api = _android_api(toolchain)
    detalle = (
        "no se encontró ningún AndroidManifest.xml"
        if not manifests
        else "no se encontró el <service> de Fiscalberry en ningún manifest"
    )
    mensaje = f"[p4a_hook] No se pudo inyectar foregroundServiceType: {detalle} (cwd={Path.cwd()})"

    if android_api and int(android_api) >= 34:
        raise RuntimeError(
            mensaje + f". Con target API {android_api} el servicio no arrancaría: se aborta el build."
        )
    print("[p4a_hook] ⚠ " + mensaje)


def before_apk_assemble(toolchain):
    """Segunda pasada: idempotente, cubre variaciones de orden entre versiones de p4a."""
    after_apk_build(toolchain)
