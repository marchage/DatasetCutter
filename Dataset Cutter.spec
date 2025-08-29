# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['entry.py'],
    pathex=[],
    binaries=[],
    datas=[('app/templates', 'app/templates'), ('app/static', 'app/static')],
    hiddenimports=['fastapi', 'uvicorn', 'jinja2', 'ffmpeg', 'ffmpeg._run', 'ffmpeg.nodes'],
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
    [],
    exclude_binaries=True,
    name='Dataset Cutter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/DatasetCutter.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Dataset Cutter',
)
app = BUNDLE(
    coll,
    name='Dataset Cutter.app',
    icon='assets/DatasetCutter.icns',
    bundle_identifier=None,
)
