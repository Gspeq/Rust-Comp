from __future__ import annotations

import threading
from collections.abc import Callable
from tkinter import messagebox
from typing import Any

import customtkinter as ctk


ACCENT = "#d97706"
SUCCESS = "#22c55e"
DANGER = "#ef4444"
MUTED = ("#64748b", "#94a3b8")


class SectionCard(ctk.CTkFrame):
    def __init__(self, master, title: str, subtitle: str = "", **kwargs):
        super().__init__(master, corner_radius=12, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=17, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        if subtitle:
            ctk.CTkLabel(
                self,
                text=subtitle,
                text_color=MUTED,
                anchor="w",
                justify="left",
                wraplength=700,
            ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
            self.content_row = 2
        else:
            self.content_row = 1


class MetricCard(ctk.CTkFrame):
    def __init__(self, master, title: str, value: str = "—", detail: str = ""):
        super().__init__(master, corner_radius=12)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, text_color=MUTED, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=14, pady=(12, 2)
        )
        self.value_label = ctk.CTkLabel(
            self, text=value, font=ctk.CTkFont(size=24, weight="bold"), anchor="w"
        )
        self.value_label.grid(row=1, column=0, sticky="ew", padx=14)
        self.detail_label = ctk.CTkLabel(
            self, text=detail, text_color=MUTED, anchor="w"
        )
        self.detail_label.grid(row=2, column=0, sticky="ew", padx=14, pady=(2, 12))

    def set(self, value: str, detail: str = "") -> None:
        self.value_label.configure(text=value)
        self.detail_label.configure(text=detail)


def run_in_worker(
    owner: ctk.CTkBaseClass,
    work: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    def target() -> None:
        try:
            result = work()
        except Exception as exc:
            callback = on_error or (lambda error: messagebox.showerror("Rust Companion+", str(error)))
            owner.after(0, lambda error=exc: callback(error))
        else:
            owner.after(0, lambda value=result: on_success(value))

    threading.Thread(target=target, daemon=True).start()


def safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return default


def safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return default
