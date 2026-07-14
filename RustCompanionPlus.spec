# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

project_root = Path(SPECPATH)
datas = [(str(project_root / "rust_companion_plus" / "data"), "rust_companion_plus/data")]
binaries = []
hiddenimports = [
    "rust_companion_plus.app",
    "rust_companion_plus.bootstrap",
    "rust_companion_plus.services.pairing",
    "rust_companion_plus.services.fcm_registration",
    "rust_companion_plus.services.server_finder",
    "rust_companion_plus.services.rustplus_client",
    "push_receiver",
    "betterproto",
    "grpclib",
    "google.protobuf",
    "cryptography",
    "http_ece",
    "oscrypto",
]

for package in ("customtkinter", "rustplus", "push_receiver", "PIL", "platformdirs", "webview"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
    except Exception:
        continue
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

analysis = Analysis(
    [str(project_root / "launcher.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="RustCompanionPlus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

