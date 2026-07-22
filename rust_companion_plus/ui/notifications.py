from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

import customtkinter as ctk

from rust_companion_plus.services.deal_notifications import (
    DealAlert,
    normalize_notification_settings,
)
from rust_companion_plus.ui.common import ACCENT, MUTED


CREATE_NO_WINDOW = 0x08000000


def _powershell_literal(value: str, limit: int) -> str:
    cleaned = " ".join(str(value or "").replace("\x00", "").split())
    return cleaned[:limit].replace("'", "''")


def show_windows_notification(
    alerts: Sequence[DealAlert],
    *,
    seconds: int,
    sound: bool,
) -> bool:
    """Send a native Windows notification that can surface over fullscreen apps."""
    if os.name != "nt" or not alerts:
        return False

    top = alerts[0]
    extra = len(alerts) - 1
    title = _powershell_literal(top.title, 63)
    body = top.message
    if extra:
        body += f" Plus {extra} more new alert-worthy listing(s)."
    body = _powershell_literal(body, 255)
    duration_ms = max(5, min(60, int(seconds))) * 1000
    icon = "Warning" if top.severity >= 3 else "Info"

    # System.Windows.Forms.NotifyIcon routes through the Windows notification
    # area. Unlike a Tk window, it remains useful while Rust is fullscreen and
    # also leaves a record in Windows Notification Center when Windows permits.
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::{icon}
$notify.BalloonTipTitle = '{title}'
$notify.BalloonTipText = '{body}'
$notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::{icon}
$notify.Visible = $true
$notify.ShowBalloonTip({duration_ms})
Start-Sleep -Milliseconds {duration_ms + 1200}
$notify.Dispose()
"""
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, ValueError):
        return False

    # NotifyIcon controls its own sound. A separate app bell is only needed for
    # the in-app fallback, so this argument is intentionally retained for API
    # clarity and future native-sound controls.
    _ = sound
    return True


class DealNotificationCenter:
    """Native Windows plus non-modal in-app marketplace notifications."""

    def __init__(self, owner: ctk.CTk) -> None:
        self.owner = owner
        self._window: ctk.CTkToplevel | None = None
        self._dismiss_job: Any = None

    def publish(
        self,
        alerts: Sequence[DealAlert],
        *,
        settings: Any,
        on_open_shops: Callable[[], None],
        force: bool = False,
    ) -> None:
        configured = normalize_notification_settings(settings)
        if not alerts or (not configured["enabled"] and not force):
            return

        native_sent = show_windows_notification(
            alerts,
            seconds=configured["popup_seconds"],
            sound=configured["sound"],
        )
        self.dismiss()

        top = alerts[0]
        extra = len(alerts) - 1
        window = ctk.CTkToplevel(self.owner)
        self._window = window
        window.title("Rust Companion+ marketplace alert")
        window.resizable(False, False)
        try:
            window.transient(self.owner)
            window.attributes("-topmost", True)
        except Exception:
            pass

        card = ctk.CTkFrame(
            window,
            width=430,
            corner_radius=12,
            border_width=1,
            border_color=("#64748b", "#475569"),
        )
        card.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=top.title,
            font=ctk.CTkFont(size=17, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(13, 4))

        summary = top.message
        if extra:
            summary += f"\n\nPlus {extra} more new alert-worthy listing(s)."
        if native_sent:
            summary += "\n\nAlso sent to Windows Notification Center."
        ctk.CTkLabel(
            card,
            text=summary,
            text_color=MUTED,
            justify="left",
            anchor="w",
            wraplength=390,
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 13))
        buttons.grid_columnconfigure((0, 1), weight=1)

        def open_shops() -> None:
            self.dismiss()
            on_open_shops()

        ctk.CTkButton(
            buttons,
            text="Open Shops",
            fg_color=ACCENT,
            command=open_shops,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(
            buttons,
            text="Dismiss",
            fg_color="transparent",
            border_width=1,
            command=self.dismiss,
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

        window.update_idletasks()
        width = max(430, window.winfo_reqwidth())
        height = max(190, window.winfo_reqheight())
        x = max(
            0,
            self.owner.winfo_rootx()
            + self.owner.winfo_width()
            - width
            - 24,
        )
        y = max(0, self.owner.winfo_rooty() + 48)
        window.geometry(f"{width}x{height}+{x}+{y}")

        if configured["sound"] and not native_sent:
            try:
                self.owner.bell()
            except Exception:
                pass
        self._dismiss_job = self.owner.after(
            configured["popup_seconds"] * 1000,
            self.dismiss,
        )

    def dismiss(self) -> None:
        if self._dismiss_job is not None:
            try:
                self.owner.after_cancel(self._dismiss_job)
            except Exception:
                pass
            self._dismiss_job = None
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
