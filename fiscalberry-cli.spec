# -*- mode: python ; coding: utf-8 -*-

import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
sys.path.insert(0, os.path.join(os.getcwd(), 'build_tools'))
from fiscalberry.version import VERSION  # noqa: E402
import win_version_info  # noqa: E402

# Metadatos del .exe (empresa, producto, version). Sin esto el binario aparece
# en Windows como un archivo anonimo, lo que lo hace ver sospechoso al usuario
# y suma puntos en las heuristicas de los antivirus. El binario de la GUI ya
# los tenia; el de consola no.
version_info = win_version_info.generar('fiscalberry-cli', VERSION)

a = Analysis(
    ['src/fiscalberry/cli/main.py'],
    pathex=[],
    binaries=[],
    datas=[('./capabilities.json', 'escpos')],
    hiddenimports=[
        # Windows: driver Win32Raw requiere win32print para enviar bytes crudos
        # Si falta, cashdraw() falla silenciosamente en el binario PyInstaller
        'win32print',
        'win32api',
        'win32con',
        'pywintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='fiscalberry-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX comprime el ejecutable empaquetandolo, que es exactamente lo que hace
    # el malware para ocultar su contenido: los antivirus lo tratan como senal
    # de sospecha y es una de las causas mas comunes de falso positivo en
    # binarios de PyInstaller. El binario de la GUI ya lo tenia desactivado por
    # ese motivo; este se habia quedado en True.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['src/fiscalberry/ui/assets/fiscalberry.ico'],
    version=version_info,
)
