from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import customtkinter as ctk

from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.rustplus_client import RustPlusClient, ServerSnapshot
from rust_companion_plus.storage import JsonStore
from rust_companion_plus.ui.common import ACCENT
from rust_companion_plus.ui.tabs.dashboard import DashboardTab
from rust_companion_plus.ui.tabs.electrical import ElectricalTab
from rust_companion_plus.ui.tabs.map_tab import MapTab
from rust_companion_plus.ui.tabs.notes import NotesTab
from rust_companion_plus.ui.tabs.shops import ShopsTab
from rust_companion_plus.ui.tabs.team import TeamTab
from rust_companion_plus.ui.tabs.threats import ThreatsTab
from rust_companion_plus.ui.tabs.tools import ToolsTab


@dataclass
class AppContext:
    store: JsonStore
    rust: RustPlusClient
    credentials: RustCredentials
    snapshot: ServerSnapshot | None = None
    map_image: Any = None
    heatmap_bundle: Any = None
    app: "RustCompanionApp | None" = field(default=None, repr=False)

    def notify_data_changed(self) -> None:
        if self.app is not None:
            self.app.notify_data_changed()


class RustCompanionApp(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        super().__init__()

        self.title("Rust Companion+")
        self.geometry("1480x900")
        self.minsize(1180, 720)

        store = JsonStore()
        credentials = RustCredentials.from_dict(store.get("credentials", {}))
        self.context = AppContext(store, RustPlusClient(), credentials)
        self.context.app = self

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=210, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self.sidebar,
            text="RUST\nCOMPANION+",
            justify="left",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w", padx=22, pady=(24, 22))

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.tabs = {
            "Overview": DashboardTab(self.content, self.context),
            "Map": MapTab(self.content, self.context),
            "Shops": ShopsTab(self.content, self.context),
            "Team": TeamTab(self.content, self.context),
            "Threats": ThreatsTab(self.content, self.context),
            "Electrical": ElectricalTab(self.content, self.context),
            "Tools": ToolsTab(self.content, self.context),
            "Notes": NotesTab(self.content, self.context),
        }

        for name in self.tabs:
            button = ctk.CTkButton(
                self.sidebar,
                text=name,
                anchor="w",
                fg_color="transparent",
                hover_color=("#d1d5db", "#28303b"),
                command=lambda selected=name: self.show_tab(selected),
            )
            button.pack(fill="x", padx=12, pady=3)

        self.connection_badge = ctk.CTkLabel(
            self.sidebar,
            text="● Offline",
            text_color=("#991b1b", "#f87171"),
            anchor="w",
        )
        self.connection_badge.pack(side="bottom", fill="x", padx=22, pady=20)

        self.current_tab = ""
        self.show_tab("Overview")

    def show_tab(self, name: str) -> None:
        if self.current_tab:
            self.tabs[self.current_tab].grid_forget()
        self.current_tab = name
        self.tabs[name].grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        refresh = getattr(self.tabs[name], "refresh", None)
        if callable(refresh):
            refresh()

    def notify_data_changed(self) -> None:
        online = self.context.snapshot is not None
        self.connection_badge.configure(
            text="● Connected" if online else "● Offline",
            text_color=("#166534", "#4ade80") if online else ("#991b1b", "#f87171"),
        )
        for tab in self.tabs.values():
            callback = getattr(tab, "on_context_updated", None)
            if callable(callback):
                callback()
