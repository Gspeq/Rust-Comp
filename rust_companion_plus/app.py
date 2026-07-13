from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

import customtkinter as ctk

from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.battlemetrics_client import BattleMetricsServer
from rust_companion_plus.services.live_sync import IntegrationSettings, LiveSyncResult, LiveSyncService
from rust_companion_plus.services.rustmaps_client import RustMapMetadata
from rust_companion_plus.services.rustplus_client import RustPlusClient, ServerSnapshot
from rust_companion_plus.services.server_detection import ServerCandidate, normalize_host
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
    live_sync: LiveSyncService
    credentials: RustCredentials
    settings: IntegrationSettings
    snapshot: ServerSnapshot | None = None
    map_image: Any = None
    heatmap_bundle: Any = None
    detected_server: ServerCandidate | None = None
    battlemetrics_server: BattleMetricsServer | None = None
    rustmaps_map: RustMapMetadata | None = None
    map_cache_dir: Any = None
    rustplus_connected: bool = False
    sync_in_progress: bool = False
    sync_status: str = "Not synced yet"
    sync_warnings: list[str] = field(default_factory=list)
    last_synced_at: str = ""
    app: "RustCompanionApp | None" = field(default=None, repr=False)

    def notify_data_changed(self) -> None:
        if self.app is not None:
            self.app.notify_data_changed()

    def save_credential_profile(self, credentials: RustCredentials, server_id: str = "") -> None:
        if not credentials.host:
            return
        profiles = dict(self.store.get("credential_profiles", {}) or {})
        profiles[normalize_host(credentials.host)] = credentials.to_dict()
        if server_id:
            profiles[str(server_id)] = credentials.to_dict()
        self.store.set("credential_profiles", profiles)


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
        settings = IntegrationSettings.from_dict(store.get("integration_settings", {}))
        rust = RustPlusClient()
        self.context = AppContext(
            store=store,
            rust=rust,
            live_sync=LiveSyncService(rustplus=rust),
            credentials=credentials,
            settings=settings,
        )
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
        self.after(1800, self._auto_sync_tick)

    def show_tab(self, name: str) -> None:
        if self.current_tab:
            self.tabs[self.current_tab].grid_forget()
        self.current_tab = name
        self.tabs[name].grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        refresh = getattr(self.tabs[name], "refresh", None)
        if callable(refresh):
            refresh()

    def _auto_sync_tick(self) -> None:
        if self.context.settings.auto_sync_enabled:
            self.run_live_sync(manual=False)
        interval_ms = max(30, self.context.settings.sync_interval_seconds) * 1000
        self.after(interval_ms, self._auto_sync_tick)

    def run_live_sync(
        self,
        *,
        manual: bool = False,
        on_complete: Callable[[LiveSyncResult], None] | None = None,
    ) -> None:
        if self.context.sync_in_progress:
            return
        self.context.sync_in_progress = True
        self.context.sync_status = "Detecting active Rust server…"
        self.notify_data_changed()

        credentials = self.context.credentials
        settings = self.context.settings
        profiles = dict(self.context.store.get("credential_profiles", {}) or {})

        def target() -> None:
            try:
                result = self.context.live_sync.refresh(
                    credentials,
                    settings,
                    credential_profiles=profiles,
                )
            except Exception as exc:
                self.after(0, lambda: self._sync_failed(exc, manual))
            else:
                self.after(0, lambda: self._sync_succeeded(result, on_complete))

        threading.Thread(target=target, daemon=True).start()

    def _sync_succeeded(
        self,
        result: LiveSyncResult,
        on_complete: Callable[[LiveSyncResult], None] | None,
    ) -> None:
        context = self.context
        context.sync_in_progress = False
        context.detected_server = result.detected
        context.battlemetrics_server = result.battlemetrics_server
        context.rustmaps_map = result.rustmaps_map
        context.credentials = result.credentials
        context.snapshot = result.snapshot
        context.rustplus_connected = result.rustplus_connected
        context.sync_warnings = result.warnings
        context.last_synced_at = result.synced_at
        context.sync_status = result.summary
        if result.map_image is not None:
            context.map_image = result.map_image
        if result.heatmap_bundle is not None:
            context.heatmap_bundle = result.heatmap_bundle
        if result.map_cache_dir is not None:
            context.map_cache_dir = result.map_cache_dir
            parsed_dir = result.map_cache_dir / "parsed"
            if parsed_dir.exists():
                context.store.set("heatmap_source_dir", str(parsed_dir))
        context.store.set("credentials", result.credentials.to_dict())
        server_id = result.battlemetrics_server.server_id if result.battlemetrics_server else ""
        if result.credentials.is_complete():
            context.save_credential_profile(result.credentials, server_id)
        context.notify_data_changed()
        if on_complete:
            on_complete(result)

    def _sync_failed(self, exc: Exception, manual: bool) -> None:
        self.context.sync_in_progress = False
        self.context.sync_status = f"Sync failed: {exc}"
        self.context.sync_warnings = [str(exc)]
        self.context.notify_data_changed()
        if manual:
            from tkinter import messagebox

            messagebox.showerror("Live server sync failed", str(exc))

    def notify_data_changed(self) -> None:
        context = self.context
        if context.sync_in_progress:
            text = "● Syncing"
            color = ("#92400e", "#fbbf24")
        elif context.rustplus_connected:
            text = "● Rust+ live"
            color = ("#166534", "#4ade80")
        elif context.snapshot is not None:
            text = "● Server found"
            color = ("#1d4ed8", "#60a5fa")
        else:
            text = "● Offline"
            color = ("#991b1b", "#f87171")
        self.connection_badge.configure(text=text, text_color=color)
        for tab in self.tabs.values():
            callback = getattr(tab, "on_context_updated", None)
            if callable(callback):
                callback()
        map_tab = self.tabs.get("Map")
        if map_tab is not None:
            for method_name in ("refresh_resource_counts", "refresh_hotspots"):
                method = getattr(map_tab, method_name, None)
                if callable(method):
                    method()
