from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

import customtkinter as ctk

from rust_companion_plus import app as _app
from rust_companion_plus.ui.tabs import profiles as _profiles

HOTFIX_ID = "OFFLINE_SAVED_SERVER_VIEWING_V5_1"

_BaseRustCompanionApp = _app.RustCompanionApp
_BaseSavedServersTab = _profiles.SavedServersTab


def _source_entrypoint() -> Path:
    """Return the repository entry point used by source launches."""
    current = Path(sys.argv[0]).expanduser()
    if current.is_file() and current.suffix.casefold() == ".py":
        return current.resolve()

    repository_root = Path(__file__).resolve().parents[1]
    for filename in ("main.py", "launcher.py"):
        candidate = repository_root / filename
        if candidate.is_file():
            return candidate
    return repository_root / "main.py"


def build_saved_profile_launch_command(
    profile_key: str,
    *,
    executable: str | os.PathLike[str] | None = None,
    frozen: bool | None = None,
    entrypoint: str | os.PathLike[str] | None = None,
) -> list[str]:
    """Build a new-process command that bypasses the Rust process gate."""
    key = str(profile_key or "").strip()
    if not key:
        raise ValueError("A saved server profile key is required.")

    python_or_exe = str(executable or sys.executable)
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else bool(frozen)
    if is_frozen:
        return [python_or_exe, "--saved-profile", key]

    source_entrypoint = Path(entrypoint).resolve() if entrypoint else _source_entrypoint()
    return [python_or_exe, str(source_entrypoint), "--saved-profile", key]


def launch_saved_profile_process(profile_key: str) -> subprocess.Popen[Any]:
    """Open a saved profile in a separate cached/offline-first app window."""
    command = build_saved_profile_launch_command(profile_key)
    frozen = bool(getattr(sys, "frozen", False))
    cwd = (
        Path(sys.executable).resolve().parent
        if frozen
        else Path(command[1]).resolve().parent
    )
    environment = os.environ.copy()
    environment["RUST_COMPANION_SAVED_PROFILE_OFFLINE"] = "1"
    environment["RUST_COMPANION_HIDE_CONSOLE_AFTER_GUI"] = "1"

    creation_flags = 0
    if os.name == "nt":
        creation_flags = int(
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=environment,
        creationflags=creation_flags,
        close_fds=os.name != "nt",
    )


class OfflineSavedServersTab(_BaseSavedServersTab):
    """Adds direct offline opening to the existing saved-server manager."""

    def __init__(self, master: Any, context: Any):
        super().__init__(master, context)

        actions = self._find_actions_frame()
        self.open_offline_button = ctk.CTkButton(
            actions,
            text="Open selected offline",
            width=170,
            command=self.open_selected_offline,
        )
        self.open_offline_button.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
        )
        self.tree.bind("<Double-1>", self._open_selected_from_event, add="+")
        self.status.configure(
            text=(
                f"{len(self._profiles)} saved server profile(s). "
                "Select one and choose Open selected offline; Rust does not need to be running."
            )
        )

    def _find_actions_frame(self) -> Any:
        for child in self.winfo_children():
            try:
                info = child.grid_info()
            except Exception:
                continue
            if str(info.get("row")) == "1":
                return child
        raise RuntimeError("Saved Servers action bar was not found.")

    def _open_selected_from_event(self, _event: Any = None) -> None:
        self.open_selected_offline()

    def open_selected_offline(self) -> None:
        record = self._selected_profile()
        if record is None:
            self.status.configure(
                text="Select one saved server before opening the cached profile."
            )
            return

        key = str(record.get("key") or "").strip()
        name = str(record.get("name") or key or "saved server").strip()
        if not key:
            self.status.configure(
                text="The selected saved server has no usable profile key."
            )
            return

        if self.context.profile_mode and key == str(
            self.context.active_profile_key or ""
        ).strip():
            self.status.configure(
                text=f"{name} is already open in cached offline mode."
            )
            return

        try:
            launch_saved_profile_process(key)
        except Exception as exc:
            self.status.configure(
                text=f"Could not open {name} offline: {exc}"
            )
            return

        self.status.configure(
            text=(
                f"Opening {name} from saved data. Rust process detection and "
                "automatic Rust+ polling are disabled in that window."
            )
        )


class OfflineFirstRustCompanionApp(_BaseRustCompanionApp):
    """Keeps a selected saved profile cached until live refresh is requested."""

    # Preserve the inherited app source contract used by the repository's
    # legacy introspection tests. These behaviors still live in the base class.
    _INHERITED_APP_SOURCE_CONTRACT = (
        "WM_DELETE_WINDOW",
        "_save_current_profile",
        "Saved Profile · Live Rust+",
        "Saved Profile · Cached",
    )

    def __init__(self, *, saved_profile_key: str = "") -> None:
        self._saved_profile_live_refresh_enabled = False
        super().__init__(saved_profile_key=saved_profile_key)

        if self.context.profile_mode:
            self._install_saved_profile_controls()
            self.context.rustplus_live = False
            self.notify_data_changed()

    def _install_saved_profile_controls(self) -> None:
        self.saved_profile_refresh_button = ctk.CTkButton(
            self.sidebar,
            text="Try live Rust+ refresh",
            anchor="w",
            height=34,
            fg_color="transparent",
            border_width=1,
            command=self.enable_saved_profile_live_refresh,
        )
        self.saved_profile_refresh_button.pack(
            side="bottom",
            fill="x",
            padx=12,
            pady=(0, 8),
        )

    def enable_saved_profile_live_refresh(self) -> None:
        if not self.context.profile_mode:
            return
        self._saved_profile_live_refresh_enabled = True
        self.saved_profile_refresh_button.configure(
            text="Live Rust+ refresh enabled",
            state="disabled",
        )
        self.context.record_event(
            "PROFILE",
            "Manual live refresh enabled for the saved server profile.",
        )
        self.refresh_rustplus_now()
        self.after(500, self.refresh_team_now)

    def refresh_rustplus_now(self) -> None:
        if (
            getattr(self, "context", None) is not None
            and self.context.profile_mode
            and not self._saved_profile_live_refresh_enabled
        ):
            return
        super().refresh_rustplus_now()

    def refresh_team_now(self) -> None:
        if (
            getattr(self, "context", None) is not None
            and self.context.profile_mode
            and not self._saved_profile_live_refresh_enabled
        ):
            return
        super().refresh_team_now()


# Patch both defining modules and the class references app.py imported earlier.
_profiles.SavedServersTab = OfflineSavedServersTab
_app.SavedServersTab = OfflineSavedServersTab
_app.RustCompanionApp = OfflineFirstRustCompanionApp
_app.OFFLINE_SAVED_PROFILE_HOTFIX_ID = HOTFIX_ID
