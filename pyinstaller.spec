# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

import os
import sysconfig

# Ensure the Python shared library is bundled (macOS framework build)
_binaries = []
try:
    _lib = sysconfig.get_config_var('LDLIBRARY') or ''
    _prefix = sysconfig.get_config_var('PYTHONFRAMEWORKPREFIX') or ''
    if _lib and _prefix:
        _lib_path = os.path.join(_prefix, _lib)
        if os.path.exists(_lib_path):
            _binaries.append((_lib_path, '.'))
except Exception:
    pass


a = Analysis(
    ['entry.py'],
    pathex=[],
    binaries=_binaries,
    datas=[
        ('app/templates', 'app/templates'),
        ('app/static', 'app/static'),
    ],
    hiddenimports=['fastapi', 'uvicorn', 'jinja2', 'ffmpeg', 'ffmpeg._run', 'ffmpeg.nodes', 'AppKit', 'Foundation', 'objc'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DatasetCutter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='assets/DatasetCutter.icns',
)

# Build in onedir mode so the Python framework and binaries are present at runtime
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DatasetCutter',
)

app = BUNDLE(
    coll,
    name='Dataset Cutter.app',
    icon='assets/DatasetCutter.icns',
    bundle_identifier='com.datasetcutter.app',
    info_plist={
        'CFBundleName': 'Dataset Cutter',
        'CFBundleDisplayName': 'Dataset Cutter',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1',
    }
)
