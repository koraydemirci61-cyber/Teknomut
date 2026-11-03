# -*- mode: python ; coding: utf-8 -*-
"""Single-file windowed Depkont build for a 64-bit Windows PC without Python."""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = [
    "pythoncom",
    "pywintypes",
    "win32api",
    "win32con",
    "win32event",
    "win32gui",
    "win32process",
    "win32timezone",
    "win32com",
    "win32com.client",
]
hiddenimports += collect_submodules("openpyxl")
hiddenimports += collect_submodules("win32com")

a = Analysis(
    ["depkont_entry.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
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
    name="Depkont",
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
)
