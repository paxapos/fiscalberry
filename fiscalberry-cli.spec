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
    # Este binario si tiene consola, pero corriendo como servicio de Windows
    # tampoco hay stdout/stderr. Mismo blindaje que en la GUI: el hook no hace
    # nada si los streams ya existen.
    runtime_hooks=['build_tools/pyi_rth_consola.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Modo ONEDIR (EXE sin binarios + COLLECT), no onefile.
#
# Un binario onefile lleva todo comprimido adentro y, en cada arranque, se
# descomprime solo en una carpeta temporal y se ejecuta desde ahi. Eso es un
# patron clasico de malware y de los que mas falsos positivos genera en los
# antivirus. Ademas arranca mas lento, porque descomprime ~65 MB cada vez.
#
# En onedir el ejecutable y sus dependencias quedan a la vista en una carpeta:
# nada se auto-extrae en runtime. Para el usuario cambia poco, porque los
# releases ya se distribuian comprimidos: ahora el .zip/.tar.gz trae una
# carpeta en vez de un unico archivo.
#
# El auto-updater reemplaza la carpeta entera; ver
# src/fiscalberry/common/updater/appliers.py
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
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

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='fiscalberry-cli',
)
