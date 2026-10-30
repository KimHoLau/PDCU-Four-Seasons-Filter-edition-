# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['tools/dng_season_gui.py'],
    pathex=['tools'],
    binaries=[],
    datas=[('tools/season.ico', '.'),
           ('tools/assets/pdcu_mod_logo_96.png', 'assets'),
           ('tools/assets/spring.png', 'assets'),
           ('tools/assets/summer.png', 'assets'),
           ('tools/assets/autumn.png', 'assets'),
           ('tools/assets/winter.png', 'assets')],
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
    name='PDCU-Season-Params',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['tools/season.ico'],
    version='tools/version_info.txt',
)
