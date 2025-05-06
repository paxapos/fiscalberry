# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src/fiscalberry/gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('./capabilities.json', 'escpos'),
        ('src/fiscalberry/ui/kv', 'fiscalberry/ui/kv')
    ],
    hiddenimports=[],
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
    version='file_version_info.txt',  # Add a version file (see below)
    uac_admin=False,  # Don't request admin privileges unless necessary
)
