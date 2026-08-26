# -*- mode: python ; coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
sys.path.insert(0, os.path.join(os.getcwd(), 'build_tools'))
from fiscalberry.version import VERSION  # noqa: E402
import win_version_info  # noqa: E402

# Se genera a partir de version.py en vez de mantenerse a mano: el archivo
# estatico anterior declaraba la version 2.1.0.0 cuando el producto ya iba por
# la 3.5.x. Un ejecutable que dice ser una version que no es no ayuda a que
# Windows ni el usuario confien en el.
version_info = win_version_info.generar('fiscalberry-gui', VERSION)

# Dependencias exclusivas de Windows (SDL2, GLEW)
kivy_deps_trees = []
if sys.platform == 'win32':
    from kivy_deps import sdl2, glew
    kivy_deps_trees = [Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)]

a = Analysis(
    ['src/fiscalberry/desktop/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('./capabilities.json', 'escpos'),
        ('src/fiscalberry/ui/kv', 'fiscalberry/ui/kv'),
        ('src/fiscalberry/ui/assets/fiscalberry.ico', 'fiscalberry/ui/assets/'),
        ('src/fiscalberry/ui/assets', 'fiscalberry/ui/assets')
    ],
    hiddenimports=[
        # Windows: driver Win32Raw requiere win32print para enviar bytes crudos
        # Si falta, cashdraw() falla silenciosamente en el binario PyInstaller
        'win32print',
        'win32api',
        'win32con',
        'pywintypes',
        'pkg_resources.py2_warn',
        'fiscalberry.ui.fiscalberry_app',
        'fiscalberry.common.Configberry',
        'fiscalberry.common.fiscalberry_logger',
        'pywin32',
    ],
    hookspath=[],
    hooksconfig={},
    # Con console=False, PyInstaller deja sys.stdout/sys.stderr en None y
    # cualquier escritura a consola aborta el arranque. El hook los reemplaza
    # antes de que corra nada de la app.
    runtime_hooks=['build_tools/pyi_rth_consola.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Modo ONEDIR (EXE sin binarios + COLLECT), no onefile. Ver el comentario
# equivalente en fiscalberry-cli.spec: onefile se auto-extrae en runtime, que
# es un patron de malware y una fuente habitual de falsos positivos.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='fiscalberry-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['src/fiscalberry/ui/assets/fiscalberry.ico'],
    version=version_info,
    uac_admin=False,
    # Configuraciones adicionales para evitar falsos positivos
    manifest=None,
    resources=[],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    *kivy_deps_trees,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='fiscalberry-gui',
)
