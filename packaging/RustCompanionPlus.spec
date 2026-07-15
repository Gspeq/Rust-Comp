# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    copy_metadata,
)


# PyInstaller exposes SPECPATH as the directory containing this spec.
# This file lives in <repo>/packaging, so its parent is the repository.
SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent
ENTRYPOINT = ROOT / "main.py"

if not ENTRYPOINT.is_file():
    raise SystemExit(
        "Rust Companion+ build entrypoint was not found: "
        f"{ENTRYPOINT}"
    )

ICON = ROOT / "packaging" / "rust_companion_plus.ico"
VERSION_FILE = (
    ROOT / "packaging" / "windows_version_info.txt"
)

datas = []
binaries = []
hiddenimports = []

for package in (
    "customtkinter",
    "PIL",
    "platformdirs",
    "psutil",
    "rustplus",
    "websockets",
    "webview",
    "push_receiver",
):
    try:
        package_datas, package_binaries, package_hidden = (
            collect_all(package)
        )
    except Exception:
        continue
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

for package in (
    "customtkinter",
    "Pillow",
    "platformdirs",
    "psutil",
    "rustplus",
    "pywebview",
):
    try:
        datas += copy_metadata(package)
    except Exception:
        pass

for module in (
    "webview",
    "webview.platforms",
    "websockets.legacy.client",
    "websockets.legacy.protocol",
    "push_receiver",
):
    try:
        hiddenimports += collect_submodules(module)
    except Exception:
        pass

project_data = ROOT / "rust_companion_plus" / "data"
if project_data.is_dir():
    datas.append(
        (
            str(project_data),
            "rust_companion_plus/data",
        )
    )

analysis = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "rust_companion_plus.debug_tools",
        "tests",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="RustCompanionPlus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=str(ICON) if ICON.is_file() else None,
    version=(
        str(VERSION_FILE)
        if VERSION_FILE.is_file()
        else None
    ),
    uac_admin=False,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RustCompanionPlus",
)
