from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tkinter import messagebox
from typing import Any


UNINSTALL_REGISTRY_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    r"\RustCompanionPlus_is1"
)


def installed_application_dir() -> Path:
    return Path(sys.executable).resolve().parent


def find_uninstaller(
    search_root: Path | None = None,
) -> Path | None:
    root = Path(search_root or installed_application_dir())
    candidates = sorted(
        (
            path
            for path in root.glob("unins*.exe")
            if path.is_file()
        ),
        key=lambda path: path.name.casefold(),
    )
    if candidates:
        return candidates[-1]

    if os.name != "nt":
        return None

    try:
        import winreg
    except ImportError:
        return None

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, UNINSTALL_REGISTRY_KEY) as key:
                raw, _kind = winreg.QueryValueEx(
                    key,
                    "UninstallString",
                )
        except OSError:
            continue

        value = str(raw or "").strip()
        if value.startswith('"') and '"' in value[1:]:
            value = value.split('"', 2)[1]
        else:
            value = value.split(" ", 1)[0]
        candidate = Path(value)
        if candidate.is_file():
            return candidate

    return None


def request_uninstall(parent: Any = None) -> bool:
    uninstaller = find_uninstaller()
    if uninstaller is None:
        messagebox.showinfo(
            "Rust Companion+ is not installed",
            (
                "No Windows installer registration was found.\n\n"
                "Build and install Rust Companion+ with the release "
                "builder before using this button."
            ),
            parent=parent,
        )
        return False

    confirmed = messagebox.askyesno(
        "Uninstall Rust Companion+?",
        (
            "This removes the installed program and all associated "
            "Rust Companion+ application data, including saved server "
            "profiles, maps, pairing credentials, caches, and logs.\n\n"
            "This cannot be undone. Continue?"
        ),
        icon="warning",
        parent=parent,
    )
    if not confirmed:
        return False

    try:
        subprocess.Popen(
            [str(uninstaller)],
            cwd=str(uninstaller.parent),
            close_fds=True,
        )
    except OSError as exc:
        messagebox.showerror(
            "Unable to start uninstaller",
            str(exc),
            parent=parent,
        )
        return False

    if parent is not None:
        try:
            parent.after(250, parent.destroy)
        except Exception:
            pass
    return True
