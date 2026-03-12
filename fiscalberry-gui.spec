# -*- mode: python ; coding: utf-8 -*-
from kivy_deps import sdl2, glew

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
    *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
    [],
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
    version='file_version_info.txt',
    uac_admin=False,
    # Configuraciones adicionales para evitar falsos positivos
    manifest=None,
    resources=[],
)
