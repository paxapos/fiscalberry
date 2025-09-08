# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/fiscalberry/gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src/fiscalberry/ui/assets', 'fiscalberry/ui/assets'),
        ('src/fiscalberry/common/assets', 'fiscalberry/common/assets'),
    ],
    hiddenimports=[
        'kivy.garden',
        'fiscalberry.ui.fiscalberry_app',
        'fiscalberry.common.Configberry',
        'fiscalberry.common.fiscalberry_logger',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    upx=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='fiscalberry-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/fiscalberry.ico',
    version='file_version_info.txt',
)
