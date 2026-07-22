from __future__ import annotations

import customtkinter as ctk

from rust_companion_plus.services.guide_catalog import (
    GUIDE_LAST_UPDATED,
    GUIDE_SECTIONS,
    GUIDE_VERSION,
    render_section,
)
from rust_companion_plus.ui.common import ACCENT, MUTED


class GuideWindow:
    """Reusable contextual guide opened by the small Guide button on every tab."""

    def __init__(self, owner: ctk.CTk) -> None:
        self.owner = owner
        self.window: ctk.CTkToplevel | None = None
        self.section_menu: ctk.CTkOptionMenu | None = None
        self.text_box: ctk.CTkTextbox | None = None

    def open(self, section: str = "Overview") -> None:
        if section not in GUIDE_SECTIONS:
            section = "Overview"

        if self.window is None or not self.window.winfo_exists():
            self._build()
        assert self.window is not None
        assert self.section_menu is not None
        self.section_menu.set(section)
        self._show_section(section)
        self.window.deiconify()
        self.window.lift()
        try:
            self.window.focus_force()
        except Exception:
            pass

    def _build(self) -> None:
        window = ctk.CTkToplevel(self.owner)
        self.window = window
        window.title("Rust Companion+ Feature Guide")
        window.geometry("920x720")
        window.minsize(700, 520)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(2, weight=1)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)

        header = ctk.CTkFrame(window, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Rust Companion+ Feature Guide",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header,
            text=f"Guide {GUIDE_VERSION} · updated {GUIDE_LAST_UPDATED}",
            text_color=MUTED,
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        controls = ctk.CTkFrame(window)
        controls.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))
        controls.grid_columnconfigure(0, weight=1)
        self.section_menu = ctk.CTkOptionMenu(
            controls,
            values=list(GUIDE_SECTIONS),
            command=self._show_section,
        )
        self.section_menu.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=10,
        )
        ctk.CTkButton(
            controls,
            text="Close",
            width=90,
            fg_color="transparent",
            border_width=1,
            command=window.withdraw,
        ).grid(row=0, column=1, padx=(0, 12), pady=10)

        self.text_box = ctk.CTkTextbox(
            window,
            wrap="word",
            font=ctk.CTkFont(size=13),
            border_width=1,
        )
        self.text_box.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(0, 18),
        )
        self.text_box.tag_config(
            "title",
            foreground=ACCENT,
        )
        self.text_box.configure(state="disabled")

    def _show_section(self, section: str) -> None:
        if self.text_box is None:
            return
        text = render_section(section)
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", text)
        self.text_box.configure(state="disabled")
        self.text_box.yview_moveto(0.0)
