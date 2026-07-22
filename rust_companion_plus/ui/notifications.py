from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import customtkinter as ctk

from rust_companion_plus.services.deal_notifications import (
    DealAlert,
    normalize_notification_settings,
)
from rust_companion_plus.ui.common import ACCENT, MUTED


class DealNotificationCenter:
    """Non-modal marketplace alerts shared by source and EXE launches."""

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

        if configured["sound"]:
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
