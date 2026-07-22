from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from tkinter import messagebox

import customtkinter as ctk

from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.rustplus_client import RustPlusClient, ServerSnapshot
from rust_companion_plus.services.resource_heatmaps import grid_reference
from rust_companion_plus.services.server_finder import DetectionReport, RustServerFinder
from rust_companion_plus.services.server_profiles import ServerProfileVault
from rust_companion_plus.storage import JsonStore
from rust_companion_plus.windows_integration import (
    hide_console_window,
    request_uninstall,
)
from rust_companion_plus.ui.common import ACCENT
from rust_companion_plus.ui.tabs.dashboard import DashboardTab
from rust_companion_plus.ui.tabs.electrical_hub import ElectricalTab
from rust_companion_plus.ui.tabs.map_enhanced import MapTab
from rust_companion_plus.ui.tabs.notes import NotesTab
from rust_companion_plus.ui.tabs.profiles import SavedServersTab
from rust_companion_plus.ui.tabs.smart_devices import SmartDevicesTab
from rust_companion_plus.ui.tabs.shops_enhanced import ShopsTab
from rust_companion_plus.ui.tabs.team import TeamTab
from rust_companion_plus.services.deal_notifications import (
    DealAlert,
    NOTIFICATION_SETTINGS_KEY,
    normalize_notification_settings,
)
from rust_companion_plus.ui.notifications import DealNotificationCenter
from rust_companion_plus.ui.guide import GuideWindow
# FEATURE_HUBS_RETENTION_V1


@dataclass

@dataclass(slots=True)
class AppStartupState:
    store: JsonStore
    vault: ServerProfileVault
    credentials: RustCredentials
    snapshot: ServerSnapshot | None
    map_image: Any
    detection: dict[str, Any]
    timeline: list[dict[str, str]]
    active_profile_key: str
    profile_record: dict[str, Any]
    profile_mode: bool
    last_live_update_at: str


def _snapshot_from_dict(
    raw: Any,
) -> ServerSnapshot | None:
    if not isinstance(raw, dict):
        return None
    server = raw.get("server")
    if not isinstance(server, dict):
        return None
    try:
        return ServerSnapshot(
            server=dict(server),
            team=list(raw.get("team") or []),
            markers=list(raw.get("markers") or []),
            server_time=str(raw.get("server_time") or ""),
        )
    except (TypeError, ValueError):
        return None


def load_startup_state(
    store: JsonStore,
    saved_profile_key: str = "",
) -> AppStartupState:
    vault = ServerProfileVault(store)
    key = str(saved_profile_key or "").strip()

    if key:
        record = vault.get(key)
        if record is None:
            raise ValueError(
                f"Saved server profile {key!r} was not found."
            )
        vault.apply_workspace(record)
        credentials = vault.credentials_for(key)
        store.set("credentials", credentials.to_dict())
        store.set("active_server_profile_key", key)
        snapshot = _snapshot_from_dict(record.get("snapshot"))
        detection = dict(record.get("detection") or {})
        timeline = list(record.get("timeline") or [])
        map_image = vault.load_map_image(record)
        return AppStartupState(
            store=store,
            vault=vault,
            credentials=credentials,
            snapshot=snapshot,
            map_image=map_image,
            detection=detection,
            timeline=timeline,
            active_profile_key=key,
            profile_record=record,
            profile_mode=True,
            last_live_update_at=str(
                record.get("live_updated_at") or ""
            ),
        )

    credentials = RustCredentials.from_dict(
        store.get("credentials", {}) or {}
    )
    raw_snapshot = store.get("bootstrap_snapshot", {}) or {}
    snapshot = _snapshot_from_dict(raw_snapshot)
    detection = dict(store.get("server_detection", {}) or {})
    timeline = list(store.get("server_timeline", []) or [])
    active_key = vault.runtime_key(
        credentials,
        detection,
    )
    profile_record = vault.get(active_key) or {}
    if active_key:
        store.set("active_server_profile_key", active_key)
    if profile_record:
        vault.apply_workspace(profile_record)
    map_image = vault.load_map_image(profile_record)
    return AppStartupState(
        store=store,
        vault=vault,
        credentials=credentials,
        snapshot=snapshot,
        map_image=map_image,
        detection=detection,
        timeline=timeline,
        active_profile_key=active_key,
        profile_record=profile_record,
        profile_mode=False,
        last_live_update_at="",
    )



def _world_grid(
    x: float,
    y: float,
    world_size: int,
) -> tuple[str, float, float]:
    if world_size <= 0:
        return "?", 0.5, 0.5

    half = world_size / 2.0
    if (
        -half - 100 <= x <= half + 100
        and -half - 100 <= y <= half + 100
    ):
        x_fraction = (x + half) / world_size
        y_fraction = (y + half) / world_size
    else:
        x_fraction = x / world_size
        y_fraction = y / world_size

    x_fraction = min(1.0, max(0.0, x_fraction))
    y_fraction = min(1.0, max(0.0, y_fraction))
    return (
        grid_reference(
            x_fraction,
            y_fraction,
            world_size,
        ),
        x_fraction,
        y_fraction,
    )


def _append_unique_store_row(
    store: JsonStore,
    key: str,
    row: dict[str, Any],
    *,
    identity: str,
    limit: int,
) -> bool:
    rows = [
        dict(item)
        for item in store.get(key, []) or []
        if isinstance(item, dict)
    ]
    if any(
        str(item.get("event_id") or "") == identity
        for item in rows
    ):
        return False

    row["event_id"] = identity
    rows.append(row)
    store.set(key, rows[-limit:])
    return True

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
    profile_mode: bool = False
    rustplus_live: bool = False
    active_profile_key: str = ""
    profile_record: dict[str, Any] = field(default_factory=dict)
    last_live_update_at: str = ""
    profile_vault: ServerProfileVault | None = field(
        default=None,
        repr=False,
    )
    app: "RustCompanionApp | None" = field(
        default=None,
        repr=False,
    )

    def notify_data_changed(self) -> None:
        if self.app is not None:
            self.app.notify_data_changed()

    def record_event(
        self,
        category: str,
        message: str,
        level: str = "info",
    ) -> None:
        event = {
            "time": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "category": category,
            "message": message,
            "level": level,
        }
        self.timeline.append(event)
        self.timeline = self.timeline[-250:]
        self.store.set("server_timeline", self.timeline)

    def apply_detection(
        self,
        report: DetectionReport,
    ) -> None:
        previous_detection = self.detection
        previous_endpoint = (
            previous_detection.get("selected") or {}
        ).get("endpoint")
        previous_bm = previous_detection.get("battlemetrics") or {}
        self.detection = report.to_dict()
        selected = report.selected

        if selected is None:
            if previous_endpoint:
                self.record_event(
                    "DETECT",
                    (
                        "Rust no longer reports an active connection "
                        f"to {previous_endpoint}."
                    ),
                    "warning",
                )
            return

        if selected.endpoint != previous_endpoint:
            self.record_event(
                "DETECT",
                (
                    f"Active Rust endpoint {selected.endpoint} selected "
                    f"from {selected.source} "
                    f"({selected.confidence:.0%} confidence)."
                ),
            )
            self.active_profile_key = selected.endpoint
            self.store.set(
                "active_server_profile_key",
                selected.endpoint,
            )
            if self.profile_vault is not None:
                self.profile_record = (
                    self.profile_vault.get(selected.endpoint) or {}
                )
                self.profile_vault.apply_workspace(
                    self.profile_record
                )
                cached_map = self.profile_vault.load_map_image(
                    self.profile_record
                )
                if cached_map is not None:
                    self.map_image = cached_map
            self._activate_profile(
                selected.host,
                selected.port,
                report,
            )

        current_bm = report.battlemetrics or {}
        if current_bm:
            old_players = int(
                previous_bm.get("players", 0) or 0
            )
            new_players = int(
                current_bm.get("players", 0) or 0
            )
            old_max = int(
                previous_bm.get("max_players", 0) or 0
            )
            new_max = int(
                current_bm.get("max_players", 0) or 0
            )
            if (
                previous_bm
                and (old_players, old_max)
                != (new_players, new_max)
            ):
                delta = new_players - old_players
                sign = "+" if delta > 0 else ""
                self.record_event(
                    "PUBLIC",
                    (
                        f"Server population {new_players}/"
                        f"{new_max or '?'} "
                        f"({sign}{delta} since the last public refresh)."
                    ),
                )
            old_status = str(
                previous_bm.get("status") or ""
            )
            new_status = str(
                current_bm.get("status") or ""
            )
            if previous_bm and old_status != new_status:
                self.record_event(
                    "PUBLIC",
                    (
                        "BattleMetrics status changed from "
                        f"{old_status or '?'} to {new_status or '?'}."
                    ),
                )

    def _activate_profile(
        self,
        host: str,
        game_port: int,
        report: DetectionReport,
    ) -> None:
        profiles = dict(
            self.store.get("credential_profiles", {}) or {}
        )
        key = f"{host}:{game_port}"
        profile = profiles.get(key)
        if profile:
            self.credentials = RustCredentials.from_dict(profile)
            self.record_event(
                "PAIR",
                f"Loaded saved Rust+ profile for {key}.",
            )
            return

        if self.credentials.host != host:
            self.credentials = RustCredentials(
                host=host,
                steam_id=self.credentials.steam_id,
            )
        else:
            self.credentials.host = host

        app_port = int(report.rust_app_port or 0)
        if app_port and not self.credentials.port:
            self.credentials.port = app_port
        self.store.set(
            "credentials",
            self.credentials.to_dict(),
        )

    def apply_snapshot(
        self,
        snapshot: ServerSnapshot,
    ) -> None:
        previous = self.snapshot
        self.snapshot = snapshot
        self.rustplus_live = True
        self.last_live_update_at = (
            datetime.now()
            .astimezone()
            .isoformat(timespec="seconds")
        )
        server = snapshot.server
        if previous is None:
            self.record_event(
                "RUST+",
                (
                    "Live snapshot connected to "
                    f"{server.get('name') or server.get('url') or 'server'}; "
                    f"population {server.get('players', 0)}/"
                    f"{server.get('max_players', 0)}."
                ),
            )
        else:
            self._record_snapshot_changes(
                previous,
                snapshot,
            )

    def apply_team_update(
        self,
        team_rows: list[dict[str, Any]],
    ) -> bool:
        """Merge one-second team state into the last full snapshot."""
        previous = self.snapshot
        if previous is None:
            return False
        current = ServerSnapshot(
            server=dict(previous.server),
            team=[dict(row) for row in team_rows],
            markers=list(previous.markers),
            server_time=previous.server_time,
        )
        self.snapshot = current
        self.rustplus_live = True
        self.last_live_update_at = (
            datetime.now()
            .astimezone()
            .isoformat(timespec="seconds")
        )
        self._record_snapshot_changes(previous, current)
        return True

    def _record_snapshot_changes(
        self,
        previous: ServerSnapshot,
        current: ServerSnapshot,
    ) -> None:
        old_server = previous.server
        new_server = current.server
        old_population = int(
            old_server.get("players", 0) or 0
        )
        new_population = int(
            new_server.get("players", 0) or 0
        )
        if old_population != new_population:
            delta = new_population - old_population
            sign = "+" if delta > 0 else ""
            self.record_event(
                "SERVER",
                (
                    f"Population {new_population}/"
                    f"{new_server.get('max_players', 0)} "
                    f"({sign}{delta})."
                ),
            )

        world_size = int(
            new_server.get("size")
            or new_server.get("map_size")
            or old_server.get("size")
            or old_server.get("map_size")
            or 0
        )

        old_members = {
            str(item.get("steam_id")): item
            for item in previous.team
        }
        new_members = {
            str(item.get("steam_id")): item
            for item in current.team
        }
        for steam_id, member in new_members.items():
            old = old_members.get(steam_id)
            name = str(
                member.get("name")
                or (old or {}).get("name")
                or steam_id
            )
            if old is None:
                self.record_event(
                    "TEAM",
                    f"{name} appeared in the live team feed.",
                )
                continue

            if bool(old.get("is_online")) != bool(
                member.get("is_online")
            ):
                state = (
                    "online"
                    if member.get("is_online")
                    else "offline"
                )
                self.record_event(
                    "TEAM",
                    f"{name} is now {state}.",
                )

            died = bool(old.get("is_alive", True)) and not bool(
                member.get("is_alive", True)
            )
            if not died:
                continue

            x = float(
                old.get("x")
                if old.get("x") is not None
                else member.get("x", 0)
                or 0
            )
            y = float(
                old.get("y")
                if old.get("y") is not None
                else member.get("y", 0)
                or 0
            )
            grid, x_fraction, y_fraction = _world_grid(
                x,
                y,
                world_size,
            )
            death_time = str(
                member.get("death_time")
                or datetime.now()
                .astimezone()
                .isoformat(timespec="seconds")
            )
            event_id = (
                f"death:{steam_id}:{death_time}:"
                f"{round(x)}:{round(y)}"
            )
            occurred_at = (
                datetime.now()
                .astimezone()
                .isoformat(timespec="seconds")
            )
            threat_row = {
                "occurred_at": occurred_at,
                "event_type": "death",
                "attacker": "Unknown",
                "victim": name,
                "weapon": "",
                "grid": grid,
                "note": (
                    "Automatic Rust+ alive→dead transition; "
                    f"last known x={x:.0f}, y={y:.0f}."
                ),
                "automatic": True,
                "source": "rustplus_team_state",
                "steam_id": steam_id,
                "x": x,
                "y": y,
                "x_fraction": x_fraction,
                "y_fraction": y_fraction,
            }
            _append_unique_store_row(
                self.store,
                "threats",
                threat_row,
                identity=event_id,
                limit=500,
            )

            if str(self.credentials.steam_id) == steam_id:
                _append_unique_store_row(
                    self.store,
                    "death_history",
                    {
                        "occurred_at": occurred_at,
                        "name": name,
                        "grid": grid,
                        "x": x,
                        "y": y,
                        "x_fraction": x_fraction,
                        "y_fraction": y_fraction,
                        "source": "rustplus_team_state",
                        "approximate": True,
                    },
                    identity=event_id,
                    limit=10,
                )

            self.record_event(
                "TEAM",
                (
                    f"{name} is reported dead near {grid}; "
                    f"last Rust+ position x={x:.0f}, y={y:.0f}."
                ),
                "warning",
            )

        event_names = {
            4: "CH47",
            5: "Cargo Ship",
            6: "Locked Crate",
            8: "Patrol Helicopter",
        }
        old_events = {
            (
                int(marker.get("type", 0) or 0),
                str(marker.get("id", "")),
            )
            for marker in previous.markers
            if int(marker.get("type", 0) or 0)
            in event_names
        }
        for marker in current.markers:
            marker_type = int(
                marker.get("type", 0) or 0
            )
            identity = (
                marker_type,
                str(marker.get("id", "")),
            )
            if (
                marker_type not in event_names
                or identity in old_events
            ):
                continue

            x = float(marker.get("x", 0) or 0)
            y = float(marker.get("y", 0) or 0)
            grid, x_fraction, y_fraction = _world_grid(
                x,
                y,
                world_size,
            )
            event_name = event_names[marker_type]
            self.record_event(
                "EVENT",
                f"{event_name} appeared near {grid}.",
            )
            _append_unique_store_row(
                self.store,
                "threats",
                {
                    "occurred_at": (
                        datetime.now()
                        .astimezone()
                        .isoformat(timespec="seconds")
                    ),
                    "event_type": "world_event",
                    "attacker": event_name,
                    "victim": "",
                    "weapon": "",
                    "grid": grid,
                    "note": (
                        f"{event_name} appeared at "
                        f"x={x:.0f}, y={y:.0f}."
                    ),
                    "automatic": True,
                    "source": "rustplus_map_marker",
                    "x": x,
                    "y": y,
                    "x_fraction": x_fraction,
                    "y_fraction": y_fraction,
                },
                identity=(
                    f"world:{marker_type}:"
                    f"{marker.get('id', '')}"
                ),
                limit=500,
            )




class RustCompanionApp(ctk.CTk):
    DETECTION_INTERVAL_MS = 10_000
    # Full server/marker snapshots are intentionally slower; lightweight
    # team-only polling preserves death accuracy without rescoring hundreds of
    # vending offers or refreshing every tab once per second.
    RUSTPLUS_INTERVAL_MS = 5_000
    TEAM_INTERVAL_MS = 1_000
    BATTLEMETRICS_INTERVAL_SECONDS = 120


    def __init__(
        self,
        *,
        saved_profile_key: str = "",
    ) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        super().__init__()

        state = load_startup_state(
            JsonStore(),
            saved_profile_key,
        )
        profile_name = str(
            state.profile_record.get("name")
            or state.active_profile_key
            or ""
        )

        self.title(
            "Rust Companion+"
            + (
                f" — {profile_name} (Saved Profile)"
                if state.profile_mode and profile_name
                else ""
            )
        )
        self.geometry("1520x920")
        self.minsize(1180, 720)

        self.context = AppContext(
            store=state.store,
            rust=RustPlusClient(),
            credentials=state.credentials,
            snapshot=state.snapshot,
            map_image=state.map_image,
            detection=state.detection,
            timeline=state.timeline,
            profile_mode=state.profile_mode,
            active_profile_key=state.active_profile_key,
            profile_record=state.profile_record,
            last_live_update_at=state.last_live_update_at,
            profile_vault=state.vault,
        )
        self.context.app = self
        self.finder = RustServerFinder(state.store)
        self._detection_busy = False
        self._rustplus_busy = False
        self._team_busy = False
        self._last_battlemetrics_refresh = 0.0
        self._last_rustplus_error = ""
        self._last_rustplus_error_at = 0.0
        self.deal_notifications = DealNotificationCenter(self)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            self,
            width=240,
            corner_radius=0,
            fg_color=("#eef2f7", "#111827"),
        )
        self.sidebar.grid(
            row=0,
            column=0,
            sticky="nsw",
        )
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self.sidebar,
            text="RUST\nCOMPANION+",
            justify="left",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=ACCENT,
        ).pack(
            anchor="w",
            padx=22,
            pady=(24, 4),
        )
        ctk.CTkLabel(
            self.sidebar,
            text="Developed by Taylor Marshall",
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color=("#64748b", "#94a3b8"),
        ).pack(
            anchor="w",
            padx=22,
            pady=(0, 10),
        )

        if state.profile_mode:
            saved_at = str(
                state.profile_record.get("saved_at") or ""
            )
            profile_text = (
                f"SAVED PROFILE\n{profile_name or state.active_profile_key}"
            )
            if saved_at:
                profile_text += f"\nSaved {saved_at[:19]}"
            self.profile_banner = ctk.CTkLabel(
                self.sidebar,
                text=profile_text,
                justify="left",
                anchor="w",
                wraplength=180,
                corner_radius=8,
                fg_color=("#e5e7eb", "#111827"),
                text_color=("#374151", "#cbd5e1"),
                font=ctk.CTkFont(size=11, weight="bold"),
            )
            self.profile_banner.pack(
                fill="x",
                padx=14,
                pady=(0, 12),
            )
        else:
            self.profile_banner = None

        self.content = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color=("#f6f8fb", "#0b111b"),
        )
        self.content.grid(
            row=0,
            column=1,
            sticky="nsew",
        )
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.tabs = {
            "Overview": DashboardTab(
                self.content,
                self.context,
            ),
            "Map": MapTab(
                self.content,
                self.context,
            ),
            "Team": TeamTab(
                self.content,
                self.context,
            ),
            "Shops": ShopsTab(
                self.content,
                self.context,
            ),
            "Electrical": ElectricalTab(
                self.content,
                self.context,
            ),
            "Smart Devices": SmartDevicesTab(
                self.content,
                self.context,
            ),
            "Saved Servers": SavedServersTab(
                self.content,
                self.context,
            ),
            "Notes": NotesTab(
                self.content,
                self.context,
            ),
        }


        self.guide_window = GuideWindow(self)

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for name in self.tabs:
            button = ctk.CTkButton(
                self.sidebar,
                text=name,
                anchor="w",
                height=40,
                corner_radius=8,
                fg_color="transparent",
                hover_color=("#dbe3ee", "#263244"),
                text_color=("#334155", "#dbe5f1"),
                font=ctk.CTkFont(
                    size=13,
                    weight="bold",
                ),
                command=lambda selected=name: self.show_tab(
                    selected
                ),
            )
            button.pack(
                fill="x",
                padx=12,
                pady=3,
            )
            self.nav_buttons[name] = button



        self.connection_badge = ctk.CTkLabel(
            self.sidebar,
            text="● Offline",
            text_color=("#991b1b", "#f87171"),
            anchor="w",
        )
        self.connection_badge.pack(
            side="bottom",
            fill="x",
            padx=22,
            pady=20,
        )

        self.uninstall_button = ctk.CTkButton(
            self.sidebar,
            text="Uninstall Rust Companion+",
            anchor="w",
            fg_color="transparent",
            hover_color=("#fee2e2", "#3f1d24"),
            border_width=1,
            border_color=("#b91c1c", "#ef4444"),
            text_color=("#991b1b", "#fca5a5"),
            command=lambda: request_uninstall(self),
        )
        self.uninstall_button.pack(
            side="bottom",
            fill="x",
            padx=12,
            pady=(0, 4),
        )

        self.current_tab = ""
        self.show_tab("Overview")
        self.protocol(
            "WM_DELETE_WINDOW",
            self._on_close,
        )
        self.after(100, self.notify_data_changed)
        self.after(350, hide_console_window)

        if not state.profile_mode:
            self.after(500, self.refresh_detection_now)

        if self.context.credentials.is_complete():
            self.after(750, self.refresh_rustplus_now)
            self.after(1_250, self.refresh_team_now)


    def open_guide(
        self,
        section: str | None = None,
    ) -> None:
        self.guide_window.open(
            section or self.current_tab or "Overview"
        )


    def show_tab(self, name: str) -> None:
        if self.current_tab:
            self.tabs[self.current_tab].grid_forget()
        self.current_tab = name
        self.tabs[name].grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=20,
            pady=20,
        )


        for label, button in self.nav_buttons.items():
            active = label == name
            button.configure(
                fg_color=(
                    ACCENT
                    if active
                    else "transparent"
                ),
                text_color=(
                    "#ffffff"
                    if active
                    else ("#334155", "#dbe5f1")
                ),
            )

        refresh = getattr(
            self.tabs[name],
            "refresh",
            None,
        )
        if callable(refresh):
            refresh()




    def notify_data_changed(
        self,
        tab_names: tuple[str, ...] | None = None,
    ) -> None:
        snapshot_available = self.context.snapshot is not None
        detected = bool(
            (
                self.context.detection.get("selected")
                or {}
            ).get("endpoint")
        )

        if self.context.profile_mode:
            if self.context.rustplus_live:
                text = "● Saved Profile · Live Rust+"
                color = ("#166534", "#4ade80")
            elif snapshot_available:
                text = "● Saved Profile · Cached"
                color = ("#1e3a8a", "#60a5fa")
            else:
                text = "● Saved Profile"
                color = ("#92400e", "#fbbf24")
        elif self.context.rustplus_live:
            text = "● Rust+ Connected"
            color = ("#166534", "#4ade80")
        elif detected:
            text = "● Server Detected"
            color = ("#92400e", "#fbbf24")
        else:
            text = "● Offline"
            color = ("#991b1b", "#f87171")

        self.connection_badge.configure(
            text=text,
            text_color=color,
        )
        targets = (
            self.tabs.values()
            if tab_names is None
            else (
                self.tabs[name]
                for name in tab_names
                if name in self.tabs
            )
        )
        for tab in targets:
            callback = getattr(
                tab,
                "on_context_updated",
                None,
            )
            if callable(callback):
                callback()



    def publish_deal_alerts(
        self,
        alerts: list[DealAlert],
        *,
        force: bool = False,
    ) -> None:
        settings = normalize_notification_settings(
            self.context.store.get(
                NOTIFICATION_SETTINGS_KEY,
                {},
            )
        )
        self.deal_notifications.publish(
            alerts,
            settings=settings,
            on_open_shops=lambda: self.show_tab("Shops"),
            force=force,
        )


    def publish_device_alerts(
        self,
        alerts: list[DealAlert],
    ) -> None:
        settings = normalize_notification_settings(
            self.context.store.get(
                NOTIFICATION_SETTINGS_KEY,
                {},
            )
        )
        self.deal_notifications.publish(
            alerts,
            settings=settings,
            on_action=lambda: self.show_tab("Smart Devices"),
            action_label="Open Smart Devices",
            force=True,
        )


    def _save_current_profile(self) -> dict[str, Any]:
        vault = self.context.profile_vault
        if vault is None:
            raise RuntimeError(
                "The server-profile vault is unavailable."
            )

        key = (
            self.context.active_profile_key
            or vault.runtime_key(
                self.context.credentials,
                self.context.detection,
            )
        )
        key = str(key or "").strip()
        if not key:
            raise RuntimeError(
                "The active game-server profile could not be identified."
            )

        snapshot = (
            self.context.snapshot.to_dict()
            if self.context.snapshot is not None
            else {}
        )
        if not snapshot and not self.context.detection:
            raise RuntimeError(
                "There is no server information to save yet."
            )

        map_tab = self.tabs.get("Map")
        parsed_map_dir = str(
            getattr(map_tab, "current_source_path", "")
            or ""
        )
        selected_resources: list[str] = []
        heatmap_world_size = 0
        if map_tab is not None:
            selector = getattr(
                map_tab,
                "selected_resources",
                None,
            )
            if callable(selector):
                selected_resources = list(selector())
            world_size_reader = getattr(
                map_tab,
                "current_world_size",
                None,
            )
            if callable(world_size_reader):
                heatmap_world_size = int(
                    world_size_reader() or 0
                )

        pending_assets = (
            self.context.profile_record.get("assets")
            if isinstance(
                self.context.profile_record,
                dict,
            )
            and isinstance(
                self.context.profile_record.get("assets"),
                dict,
            )
            else {}
        )

        record = vault.save_runtime_profile(
            key=key,
            credentials=self.context.credentials,
            snapshot=snapshot,
            detection=self.context.detection,
            timeline=self.context.timeline,
            map_image=self.context.map_image,
            pending_assets=pending_assets,
            parsed_map_dir=parsed_map_dir,
            heatmap_world_size=heatmap_world_size,
            heatmap_selected_resources=selected_resources,
            live_updated_at=self.context.last_live_update_at,
        )
        self.context.active_profile_key = key
        self.context.profile_record = record
        if snapshot:
            self.context.store.set(
                "bootstrap_snapshot",
                snapshot,
            )
        return record

    def _on_close(self) -> None:
        key = str(
            self.context.active_profile_key or ""
        ).strip()
        name = str(
            self.context.profile_record.get("name")
            if isinstance(
                self.context.profile_record,
                dict,
            )
            else ""
        ).strip()
        target = name or key or "this server"

        answer = messagebox.askyesnocancel(
            "Save server profile before closing?",
            (
                f"Save the latest available information for {target}?\n\n"
                "Yes saves server info, team status, shops and map "
                "markers, the current map, parsed-map association, "
                "timeline, and saved-profile metadata. The profile can "
                "then be opened from the bootloader with Rust closed.\n\n"
                "No closes without updating the saved archive."
            ),
            parent=self,
        )
        if answer is None:
            return
        if answer:
            try:
                self._save_current_profile()
            except Exception as exc:
                messagebox.showerror(
                    "Server profile was not saved",
                    str(exc),
                    parent=self,
                )
                return
        self.destroy()

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
        if self.context.profile_mode:
            return
        if self._detection_busy:
            return
        self._detection_busy = True

        def success(report: DetectionReport) -> None:
            self._detection_busy = False
            self.context.apply_detection(report)
            self.notify_data_changed()
            self.after(
                self.DETECTION_INTERVAL_MS,
                self.refresh_detection_now,
            )

        def failure(exc: Exception) -> None:
            self._detection_busy = False
            self.context.record_event(
                "DETECT",
                f"Detection refresh failed: {exc}",
                "error",
            )
            self.notify_data_changed()
            self.after(
                self.DETECTION_INTERVAL_MS,
                self.refresh_detection_now,
            )

        previous_endpoint = (
            self.context.detection.get("selected")
            or {}
        ).get("endpoint")

        def work() -> DetectionReport:
            session = self.finder.get_rust_process_session()
            report = self.finder.detect_once(
                enrich=False,
                require_running_process=True,
                session_started_at=(
                    session.started_at_epoch
                    if session.running
                    else None
                ),
                current_session_only=True,
            )
            selected_endpoint = (
                report.selected.endpoint
                if report.selected
                else ""
            )
            enrichment_due = (
                time.monotonic()
                - self._last_battlemetrics_refresh
                >= self.BATTLEMETRICS_INTERVAL_SECONDS
            )
            if report.selected and (
                selected_endpoint != previous_endpoint
                or enrichment_due
            ):
                report = self.finder.detect_once(
                    enrich=True,
                    require_running_process=True,
                    session_started_at=(
                        session.started_at_epoch
                    ),
                    current_session_only=True,
                )
                self._last_battlemetrics_refresh = (
                    time.monotonic()
                )
            return report

        self._background(
            work,
            success,
            failure,
        )



    def refresh_team_now(self) -> None:
        if self._team_busy:
            return
        if self._rustplus_busy:
            self.after(250, self.refresh_team_now)
            return
        if not self.context.credentials.is_complete():
            self.after(
                self.TEAM_INTERVAL_MS,
                self.refresh_team_now,
            )
            return

        self._team_busy = True

        def success(team_rows: list[dict[str, Any]]) -> None:
            self._team_busy = False
            if self.context.apply_team_update(team_rows):
                self.notify_data_changed(("Overview", "Team"))
            self.after(
                self.TEAM_INTERVAL_MS,
                self.refresh_team_now,
            )

        def failure(_exc: Exception) -> None:
            self._team_busy = False
            # The slower full-snapshot loop owns connection warnings. Team
            # polling failures are intentionally quiet to avoid timeline spam.
            self.after(
                self.TEAM_INTERVAL_MS,
                self.refresh_team_now,
            )

        self._background(
            lambda: self.context.rust.fetch_team(
                self.context.credentials
            ),
            success,
            failure,
        )


    def refresh_rustplus_now(self) -> None:
        if self._rustplus_busy:
            return
        if self._team_busy:
            self.after(250, self.refresh_rustplus_now)
            return
        if not self.context.credentials.is_complete():
            self.context.rustplus_live = False
            self.notify_data_changed()
            self.after(
                self.RUSTPLUS_INTERVAL_MS,
                self.refresh_rustplus_now,
            )
            return

        self._rustplus_busy = True

        def success(snapshot: ServerSnapshot) -> None:
            self._rustplus_busy = False
            self._last_rustplus_error = ""
            self.context.apply_snapshot(snapshot)
            self.notify_data_changed()
            self.after(
                self.RUSTPLUS_INTERVAL_MS,
                self.refresh_rustplus_now,
            )

        def failure(exc: Exception) -> None:
            self._rustplus_busy = False
            self.context.rustplus_live = False
            message = str(exc).strip() or "Unknown Rust+ failure"
            now = time.monotonic()
            if (
                message != self._last_rustplus_error
                or now - self._last_rustplus_error_at >= 30.0
            ):
                self.context.record_event(
                    "RUST+",
                    (
                        "Saved/live Rust+ refresh failed; "
                        f"cached data remains available: {message}"
                    ),
                    "warning",
                )
                self._last_rustplus_error = message
                self._last_rustplus_error_at = now
            self.connection_badge.configure(
                text="● Rust+ Reconnecting",
                text_color=("#92400e", "#fbbf24"),
            )
            self.notify_data_changed()
            self.after(
                self.RUSTPLUS_INTERVAL_MS,
                self.refresh_rustplus_now,
            )

        self._background(
            lambda: self.context.rust.fetch_snapshot(
                self.context.credentials
            ),
            success,
            failure,
        )
