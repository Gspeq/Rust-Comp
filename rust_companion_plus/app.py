from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import customtkinter as ctk

from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.rustplus_client import RustPlusClient, ServerSnapshot
from rust_companion_plus.services.server_finder import DetectionReport, RustServerFinder
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
    detection: dict[str, Any] = field(default_factory=dict)
    timeline: list[dict[str, str]] = field(default_factory=list)
    app: "RustCompanionApp | None" = field(default=None, repr=False)

    def notify_data_changed(self) -> None:
        if self.app is not None:
            self.app.notify_data_changed()

    def record_event(self, category: str, message: str, level: str = "info") -> None:
        event = {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "category": category,
            "message": message,
            "level": level,
        }
        self.timeline.append(event)
        self.timeline = self.timeline[-250:]
        self.store.set("server_timeline", self.timeline)

    def apply_detection(self, report: DetectionReport) -> None:
        previous_detection = self.detection
        previous_endpoint = (previous_detection.get("selected") or {}).get("endpoint")
        previous_bm = previous_detection.get("battlemetrics") or {}
        self.detection = report.to_dict()
        selected = report.selected

        if selected is None:
            if previous_endpoint:
                self.record_event(
                    "DETECT",
                    f"Rust no longer reports an active connection to {previous_endpoint}.",
                    "warning",
                )
            return

        if selected.endpoint != previous_endpoint:
            self.record_event(
                "DETECT",
                f"Active Rust endpoint {selected.endpoint} selected from {selected.source} "
                f"({selected.confidence:.0%} confidence).",
            )
            self._activate_profile(selected.host, selected.port, report)

        current_bm = report.battlemetrics or {}
        if current_bm:
            old_players = int(previous_bm.get("players", 0) or 0)
            new_players = int(current_bm.get("players", 0) or 0)
            old_max = int(previous_bm.get("max_players", 0) or 0)
            new_max = int(current_bm.get("max_players", 0) or 0)
            if previous_bm and (old_players, old_max) != (new_players, new_max):
                delta = new_players - old_players
                sign = "+" if delta > 0 else ""
                self.record_event(
                    "PUBLIC",
                    f"Server population {new_players}/{new_max or '?'} ({sign}{delta} since the last public refresh).",
                )
            old_status = str(previous_bm.get("status") or "")
            new_status = str(current_bm.get("status") or "")
            if previous_bm and old_status != new_status:
                self.record_event("PUBLIC", f"BattleMetrics status changed from {old_status or '?'} to {new_status or '?'}.")

    def _activate_profile(self, host: str, game_port: int, report: DetectionReport) -> None:
        profiles = dict(self.store.get("credential_profiles", {}) or {})
        key = f"{host}:{game_port}"
        profile = profiles.get(key)
        if profile:
            self.credentials = RustCredentials.from_dict(profile)
            self.record_event("PAIR", f"Loaded saved Rust+ profile for {key}.")
            return

        if self.credentials.host != host:
            # Steam ID is account-wide, while app port/token are server-specific.
            self.credentials = RustCredentials(host=host, steam_id=self.credentials.steam_id)
        else:
            self.credentials.host = host
        app_port = int(report.rust_app_port or 0)
        if app_port and not self.credentials.port:
            self.credentials.port = app_port
        self.store.set("credentials", self.credentials.to_dict())

    def apply_snapshot(self, snapshot: ServerSnapshot) -> None:
        previous = self.snapshot
        self.snapshot = snapshot
        server = snapshot.server
        if previous is None:
            self.record_event(
                "RUST+",
                f"Live snapshot connected to {server.get('name') or server.get('url') or 'server'}; "
                f"population {server.get('players', 0)}/{server.get('max_players', 0)}.",
            )
        else:
            self._record_snapshot_changes(previous, snapshot)

    def _record_snapshot_changes(self, previous: ServerSnapshot, current: ServerSnapshot) -> None:
        old_server, new_server = previous.server, current.server
        old_population = int(old_server.get("players", 0) or 0)
        new_population = int(new_server.get("players", 0) or 0)
        if old_population != new_population:
            delta = new_population - old_population
            sign = "+" if delta > 0 else ""
            self.record_event(
                "SERVER",
                f"Population {new_population}/{new_server.get('max_players', 0)} ({sign}{delta}).",
            )

        old_members = {str(item.get("steam_id")): item for item in previous.team}
        new_members = {str(item.get("steam_id")): item for item in current.team}
        for steam_id, member in new_members.items():
            old = old_members.get(steam_id)
            name = member.get("name") or steam_id
            if old is None:
                self.record_event("TEAM", f"{name} appeared in the live team feed.")
                continue
            if bool(old.get("is_online")) != bool(member.get("is_online")):
                state = "online" if member.get("is_online") else "offline"
                self.record_event("TEAM", f"{name} is now {state}.")
            if bool(old.get("is_alive", True)) and not bool(member.get("is_alive", True)):
                self.record_event("TEAM", f"{name} is reported dead.", "warning")

        event_names = {4: "CH47", 5: "Cargo Ship", 6: "Locked Crate", 8: "Patrol Helicopter"}
        old_events = {
            (int(marker.get("type", 0) or 0), str(marker.get("id", "")))
            for marker in previous.markers
            if int(marker.get("type", 0) or 0) in event_names
        }
        for marker in current.markers:
            marker_type = int(marker.get("type", 0) or 0)
            identity = (marker_type, str(marker.get("id", "")))
            if marker_type in event_names and identity not in old_events:
                self.record_event(
                    "EVENT",
                    f"{event_names[marker_type]} appeared near x={float(marker.get('x', 0) or 0):.0f}, "
                    f"y={float(marker.get('y', 0) or 0):.0f}.",
                )


class RustCompanionApp(ctk.CTk):
    DETECTION_INTERVAL_MS = 10_000
    RUSTPLUS_INTERVAL_MS = 30_000
    BATTLEMETRICS_INTERVAL_SECONDS = 120

    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        super().__init__()

        self.title("Rust Companion+")
        self.geometry("1480x900")
        self.minsize(1180, 720)

        store = JsonStore()
        credentials = RustCredentials.from_dict(store.get("credentials", {}))
        bootstrap_snapshot = None
        raw_snapshot = store.get("bootstrap_snapshot", {}) or {}
        if isinstance(raw_snapshot, dict) and raw_snapshot.get("server") is not None:
            try:
                bootstrap_snapshot = ServerSnapshot(
                    server=dict(raw_snapshot.get("server") or {}),
                    team=list(raw_snapshot.get("team") or []),
                    markers=list(raw_snapshot.get("markers") or []),
                    server_time=str(raw_snapshot.get("server_time") or ""),
                )
            except (TypeError, ValueError):
                bootstrap_snapshot = None
        self.context = AppContext(
            store,
            RustPlusClient(),
            credentials,
            snapshot=bootstrap_snapshot,
            detection=dict(store.get("server_detection", {}) or {}),
            timeline=list(store.get("server_timeline", []) or []),
        )
        self.context.app = self
        self.finder = RustServerFinder(store)
        self._detection_busy = False
        self._rustplus_busy = False
        self._last_battlemetrics_refresh = 0.0

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=225, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self.sidebar,
            text="RUST\nCOMPANION+",
            justify="left",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w", padx=22, pady=(24, 4))
        ctk.CTkLabel(
            self.sidebar,
            text="Developed by Taylor Marshall",
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color=("#64748b", "#94a3b8"),
        ).pack(anchor="w", padx=22, pady=(0, 18))

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
        self.after(500, self.refresh_detection_now)
        self.after(1_500, self.refresh_rustplus_now)

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
        detected = bool((self.context.detection.get("selected") or {}).get("endpoint"))
        if online:
            text, color = "● Rust+ Connected", ("#166534", "#4ade80")
        elif detected:
            text, color = "● Server Detected", ("#92400e", "#fbbf24")
        else:
            text, color = "● Offline", ("#991b1b", "#f87171")
        self.connection_badge.configure(text=text, text_color=color)
        for tab in self.tabs.values():
            callback = getattr(tab, "on_context_updated", None)
            if callable(callback):
                callback()

    def _background(
        self,
        work: Callable[[], Any],
        success: Callable[[Any], None],
        failure: Callable[[Exception], None],
    ) -> None:
        def target() -> None:
            try:
                result = work()
            except Exception as exc:
                self.after(0, lambda error=exc: failure(error))
            else:
                self.after(0, lambda value=result: success(value))

        threading.Thread(target=target, daemon=True).start()

    def refresh_detection_now(self) -> None:
        if self._detection_busy:
            return
        self._detection_busy = True

        def success(report: DetectionReport) -> None:
            self._detection_busy = False
            self.context.apply_detection(report)
            self.notify_data_changed()
            self.after(self.DETECTION_INTERVAL_MS, self.refresh_detection_now)

        def failure(exc: Exception) -> None:
            self._detection_busy = False
            self.context.record_event("DETECT", f"Detection refresh failed: {exc}", "error")
            self.notify_data_changed()
            self.after(self.DETECTION_INTERVAL_MS, self.refresh_detection_now)

        previous_endpoint = (self.context.detection.get("selected") or {}).get("endpoint")

        def work() -> DetectionReport:
            session = self.finder.get_rust_process_session()
            report = self.finder.detect_once(
                enrich=False,
                require_running_process=True,
                session_started_at=session.started_at_epoch if session.running else None,
                current_session_only=True,
            )
            selected_endpoint = report.selected.endpoint if report.selected else ""
            enrichment_due = (
                time.monotonic() - self._last_battlemetrics_refresh
                >= self.BATTLEMETRICS_INTERVAL_SECONDS
            )
            if report.selected and (selected_endpoint != previous_endpoint or enrichment_due):
                report = self.finder.detect_once(
                    enrich=True,
                    require_running_process=True,
                    session_started_at=session.started_at_epoch,
                    current_session_only=True,
                )
                self._last_battlemetrics_refresh = time.monotonic()
            return report

        self._background(work, success, failure)

    def refresh_rustplus_now(self) -> None:
        if self._rustplus_busy:
            return
        if not self.context.credentials.is_complete():
            self.after(self.RUSTPLUS_INTERVAL_MS, self.refresh_rustplus_now)
            return
        self._rustplus_busy = True

        def success(snapshot: ServerSnapshot) -> None:
            self._rustplus_busy = False
            self.context.apply_snapshot(snapshot)
            self.notify_data_changed()
            self.after(self.RUSTPLUS_INTERVAL_MS, self.refresh_rustplus_now)

        def failure(exc: Exception) -> None:
            self._rustplus_busy = False
            self.context.record_event("RUST+", f"Refresh failed: {exc}", "warning")
            self.notify_data_changed()
            self.after(self.RUSTPLUS_INTERVAL_MS, self.refresh_rustplus_now)

        self._background(
            lambda: self.context.rust.fetch_snapshot(self.context.credentials),
            success,
            failure,
        )
