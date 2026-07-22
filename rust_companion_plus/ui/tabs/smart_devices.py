from __future__ import annotations

import time
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any
from uuid import uuid4

import customtkinter as ctk

from rust_companion_plus.services.deal_notifications import DealAlert
from rust_companion_plus.services.rustplus_entities import (
    fetch_entities,
    set_entities_value,
)
from rust_companion_plus.services.smart_automation import (
    DEFAULT_SMART_SETTINGS,
    RULE_ACTIONS,
    RULE_CONDITIONS,
    SMART_ACTIVITY_KEY,
    SMART_RULES_KEY,
    SMART_SCENES_KEY,
    SMART_SETTINGS_KEY,
    SMART_SYSTEMS_KEY,
    append_activity,
    evaluate_rules,
    normalize_rules,
    normalize_scenes,
    normalize_smart_settings,
    normalize_systems,
    scene_plan,
    status_capacity,
    status_value,
    system_summary,
)
from rust_companion_plus.ui.common import (
    DANGER,
    MUTED,
    SUCCESS,
    run_in_worker,
    safe_int,
)


DEVICE_STORE_KEY = "smart_devices"
DEVICE_ROLES = (
    "Smart Switch",
    "Smart Alarm",
    "Storage Monitor",
    "Defense",
    "Lighting",
    "Door / Lockdown",
    "Industry",
    "Sensor",
    "Other",
)


def _normalize_device(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        entity_id = int(raw.get("entity_id") or 0)
    except (TypeError, ValueError):
        return None
    if entity_id <= 0:
        return None
    return {
        "entity_id": entity_id,
        "name": str(raw.get("name") or f"Entity {entity_id}"),
        "zone": str(raw.get("zone") or "Main Base"),
        "role": str(raw.get("role") or "Other"),
        "system": str(raw.get("system") or ""),
        "favorite": bool(raw.get("favorite", False)),
        "last_status": dict(raw.get("last_status") or {}),
        "updated_at": str(raw.get("updated_at") or ""),
    }


def normalize_devices(raw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for value in raw if isinstance(raw, list) else []:
        device = _normalize_device(value)
        if device is None or device["entity_id"] in seen:
            continue
        seen.add(device["entity_id"])
        rows.append(device)
    rows.sort(
        key=lambda row: (
            not bool(row.get("favorite")),
            str(row.get("system", "")).casefold(),
            str(row.get("zone", "")).casefold(),
            str(row.get("name", "")).casefold(),
        )
    )
    return rows


class SmartDevicesTab(ctk.CTkFrame):
    """Rust+ device console with systems, scenes, rules, and verification."""

    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.devices = normalize_devices(
            context.store.get(DEVICE_STORE_KEY, [])
        )
        self.systems = normalize_systems(
            context.store.get(SMART_SYSTEMS_KEY, []),
            self._device_ids(),
        )
        self.scenes = normalize_scenes(
            context.store.get(SMART_SCENES_KEY, []),
            self._device_ids(),
        )
        self.rules = normalize_rules(
            context.store.get(SMART_RULES_KEY, []),
            self._device_ids(),
            [row["id"] for row in self.scenes],
        )
        self.settings = normalize_smart_settings(
            context.store.get(SMART_SETTINGS_KEY, {})
        )
        self.activity = [
            dict(row)
            for row in context.store.get(SMART_ACTIVITY_KEY, []) or []
            if isinstance(row, dict)
        ]
        self._busy = False
        self._refresh_job: Any = None
        self._last_refresh_at = 0.0
        self._previous_statuses = self._status_map()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_metrics()
        self._build_tabs()
        self._render_all()
        self._schedule_auto_refresh()

    def _device_ids(self) -> list[int]:
        return [int(row["entity_id"]) for row in self.devices]

    def _status_map(self) -> dict[int, dict[str, Any]]:
        return {
            int(row["entity_id"]): dict(row.get("last_status") or {})
            for row in self.devices
        }

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Smart Base Control",
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header,
            text=(
                "Control paired Rust+ entities, group them into logical systems, "
                "run verified scenes, and evaluate local automation rules."
            ),
            text_color=MUTED,
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.grid(row=0, column=1, rowspan=2, sticky="e")
        self.auto_refresh = ctk.BooleanVar(
            value=self.settings["auto_refresh"]
        )
        self.rules_armed = ctk.BooleanVar(
            value=self.settings["rules_armed"]
        )
        self.refresh_seconds = ctk.StringVar(
            value=str(self.settings["refresh_seconds"])
        )
        ctk.CTkSwitch(
            controls,
            text="Auto refresh",
            variable=self.auto_refresh,
            command=self._settings_changed,
        ).grid(row=0, column=0, padx=5)
        ctk.CTkOptionMenu(
            controls,
            values=["3", "5", "10", "15", "30", "60"],
            variable=self.refresh_seconds,
            width=78,
            command=lambda _value: self._settings_changed(),
        ).grid(row=0, column=1, padx=5)
        ctk.CTkSwitch(
            controls,
            text="Arm rules",
            variable=self.rules_armed,
            command=self._settings_changed,
        ).grid(row=0, column=2, padx=5)
        self.live_badge = ctk.CTkLabel(
            controls,
            text="  OFFLINE  ",
            text_color=MUTED,
            corner_radius=999,
            fg_color=("#e5e7eb", "#111827"),
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.live_badge.grid(row=0, column=3, padx=(8, 0))

    def _build_metrics(self) -> None:
        metrics = ctk.CTkFrame(self, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        for column in range(5):
            metrics.grid_columnconfigure(column, weight=1)
        self.saved_metric = self._metric(metrics, 0, "Saved", "0")
        self.on_metric = self._metric(metrics, 1, "On", "0")
        self.system_metric = self._metric(metrics, 2, "Systems", "0")
        self.scene_metric = self._metric(metrics, 3, "Scenes", "0")
        self.rule_metric = self._metric(metrics, 4, "Rules armed", "0")

    @staticmethod
    def _metric(parent, column: int, title: str, value: str):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.grid(row=0, column=column, sticky="ew", padx=4)
        label = ctk.CTkLabel(
            card,
            text=f"{title.upper()}\n{value}",
            font=ctk.CTkFont(size=14, weight="bold"),
            justify="left",
            anchor="w",
        )
        label.pack(fill="x", padx=12, pady=8)
        return label

    def _build_tabs(self) -> None:
        self.tabs = ctk.CTkTabview(self, corner_radius=12)
        self.tabs.grid(row=2, column=0, sticky="nsew")
        for name in ("Devices", "Systems", "Scenes", "Rules & Activity"):
            self.tabs.add(name)

        self._build_devices_tab(self.tabs.tab("Devices"))
        self._build_systems_tab(self.tabs.tab("Systems"))
        self._build_scenes_tab(self.tabs.tab("Scenes"))
        self._build_rules_tab(self.tabs.tab("Rules & Activity"))

        self.status = ctk.CTkLabel(
            self,
            text="Add paired Rust+ entity IDs to begin.",
            text_color=MUTED,
            anchor="w",
        )
        self.status.grid(row=3, column=0, sticky="ew", pady=(7, 0))

    def _build_devices_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        add_card = ctk.CTkFrame(parent, corner_radius=10)
        add_card.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 5))
        for column in range(6):
            add_card.grid_columnconfigure(column, weight=1)

        self.name_entry = ctk.CTkEntry(
            add_card,
            placeholder_text="Device name",
        )
        self.zone_entry = ctk.CTkEntry(
            add_card,
            placeholder_text="Zone / room",
        )
        self.role_menu = ctk.CTkOptionMenu(
            add_card,
            values=list(DEVICE_ROLES),
        )
        self.role_menu.set("Smart Switch")
        self.system_entry = ctk.CTkEntry(
            add_card,
            placeholder_text="Logical system",
        )
        self.id_entry = ctk.CTkEntry(
            add_card,
            placeholder_text="Paired entity ID",
        )
        for column, widget in enumerate(
            (
                self.name_entry,
                self.zone_entry,
                self.role_menu,
                self.system_entry,
                self.id_entry,
            )
        ):
            widget.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=4,
                pady=10,
            )
        ctk.CTkButton(
            add_card,
            text="Save device",
            command=self.add_device,
        ).grid(row=0, column=5, sticky="ew", padx=4, pady=10)

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        actions.grid_columnconfigure(tuple(range(9)), weight=1)
        definitions = (
            ("Refresh selected", self.refresh_selected, "normal"),
            ("Refresh all", self.refresh_all, "normal"),
            ("Turn ON", lambda: self.set_selected(True), "normal"),
            ("Turn OFF", lambda: self.set_selected(False), "outline"),
            ("Favorite", self.toggle_favorite, "outline"),
            ("Copy ID", self.copy_selected_id, "outline"),
            ("Capture scene", self.capture_scene_from_status, "outline"),
            ("Remove", self.remove_selected, "danger"),
            ("Remove all", self.remove_all, "danger"),
        )
        for column, (text, command, style) in enumerate(definitions):
            kwargs: dict[str, Any] = {}
            if style == "outline":
                kwargs.update(fg_color="transparent", border_width=1)
            elif style == "danger":
                kwargs.update(fg_color=DANGER)
            ctk.CTkButton(
                actions,
                text=text,
                command=command,
                height=32,
                **kwargs,
            ).grid(row=0, column=column, sticky="ew", padx=2)

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=8, pady=(3, 8))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self.device_tree = ttk.Treeview(
            body,
            columns=(
                "name",
                "zone",
                "role",
                "system",
                "id",
                "state",
                "capacity",
                "checked",
            ),
            show="headings",
            selectmode="extended",
        )
        settings = (
            ("name", "Name", 150, "w"),
            ("zone", "Zone", 95, "w"),
            ("role", "Role", 110, "w"),
            ("system", "System", 110, "w"),
            ("id", "Entity ID", 90, "center"),
            ("state", "State", 70, "center"),
            ("capacity", "Capacity", 80, "center"),
            ("checked", "Last check", 115, "center"),
        )
        for name, heading, width, anchor in settings:
            self.device_tree.heading(name, text=heading)
            self.device_tree.column(
                name,
                width=width,
                minwidth=50,
                anchor=anchor,
                stretch=name in {"name", "system"},
            )
        self.device_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.device_tree.bind(
            "<<TreeviewSelect>>",
            lambda _event: self._show_selected_detail(),
        )

        self.detail = ctk.CTkTextbox(
            body,
            corner_radius=8,
            wrap="word",
        )
        self.detail.grid(row=0, column=1, sticky="nsew")

    def _build_systems_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(parent, corner_radius=10)
        form.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 5))
        form.grid_columnconfigure((0, 1, 2), weight=1)
        self.system_name = ctk.CTkEntry(
            form,
            placeholder_text="System name, e.g. North Defense",
        )
        self.system_zone = ctk.CTkEntry(
            form,
            placeholder_text="Zone",
        )
        self.system_purpose = ctk.CTkEntry(
            form,
            placeholder_text="Purpose",
        )
        self.system_critical = ctk.BooleanVar(value=False)
        self.system_name.grid(row=0, column=0, sticky="ew", padx=4, pady=8)
        self.system_zone.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self.system_purpose.grid(row=0, column=2, sticky="ew", padx=4, pady=8)
        ctk.CTkSwitch(
            form,
            text="Critical",
            variable=self.system_critical,
        ).grid(row=0, column=3, padx=6)
        ctk.CTkButton(
            form,
            text="Create from selected devices",
            command=self.create_system,
        ).grid(row=0, column=4, padx=6)

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        actions.grid_columnconfigure(tuple(range(5)), weight=1)
        for column, (text, command) in enumerate(
            (
                ("Refresh system", self.refresh_selected_system),
                ("System ON", lambda: self.set_selected_system(True)),
                ("System OFF", lambda: self.set_selected_system(False)),
                ("Create scene ON", lambda: self.scene_from_system(True)),
                ("Remove system", self.remove_system),
            )
        ):
            kwargs: dict[str, Any] = {}
            if text == "Remove system":
                kwargs["fg_color"] = DANGER
            elif "OFF" in text:
                kwargs.update(fg_color="transparent", border_width=1)
            ctk.CTkButton(
                actions,
                text=text,
                command=command,
                **kwargs,
            ).grid(row=0, column=column, sticky="ew", padx=3)

        self.system_tree = ttk.Treeview(
            parent,
            columns=(
                "name",
                "zone",
                "purpose",
                "members",
                "online",
                "on",
                "errors",
            ),
            show="headings",
            selectmode="browse",
        )
        for name, heading, width in (
            ("name", "System", 180),
            ("zone", "Zone", 110),
            ("purpose", "Purpose", 180),
            ("members", "Devices", 75),
            ("online", "Online", 75),
            ("on", "On", 75),
            ("errors", "Errors", 75),
        ):
            self.system_tree.heading(name, text=heading)
            self.system_tree.column(
                name,
                width=width,
                anchor="w" if name in {"name", "zone", "purpose"} else "center",
                stretch=name in {"name", "purpose"},
            )
        self.system_tree.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=8,
            pady=(4, 8),
        )

    def _build_scenes_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(parent, corner_radius=10)
        form.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 5))
        form.grid_columnconfigure(0, weight=1)
        self.scene_name = ctk.CTkEntry(
            form,
            placeholder_text="Scene name, e.g. Raid Mode",
        )
        self.scene_name.grid(row=0, column=0, sticky="ew", padx=6, pady=8)
        self.scene_verify = ctk.BooleanVar(
            value=self.settings["verify_scene"]
        )
        self.scene_confirm = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            form,
            text="Verify after run",
            variable=self.scene_verify,
        ).grid(row=0, column=1, padx=6)
        ctk.CTkSwitch(
            form,
            text="Confirm before run",
            variable=self.scene_confirm,
        ).grid(row=0, column=2, padx=6)
        ctk.CTkButton(
            form,
            text="Selected → ON scene",
            command=lambda: self.create_scene_from_selected(True),
        ).grid(row=0, column=3, padx=4)
        ctk.CTkButton(
            form,
            text="Selected → OFF scene",
            command=lambda: self.create_scene_from_selected(False),
            fg_color="transparent",
            border_width=1,
        ).grid(row=0, column=4, padx=4)

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        actions.grid_columnconfigure(tuple(range(5)), weight=1)
        for column, (text, command) in enumerate(
            (
                ("Run scene", self.run_selected_scene),
                ("Preview", self.preview_selected_scene),
                ("Favorite", self.favorite_scene),
                ("Duplicate", self.duplicate_scene),
                ("Remove", self.remove_scene),
            )
        ):
            ctk.CTkButton(
                actions,
                text=text,
                command=command,
                fg_color=DANGER if text == "Remove" else "transparent",
                border_width=1 if text != "Run scene" else 0,
            ).grid(row=0, column=column, sticky="ew", padx=3)

        self.scene_tree = ttk.Treeview(
            parent,
            columns=("name", "actions", "verify", "confirm"),
            show="headings",
            selectmode="browse",
        )
        for name, heading, width in (
            ("name", "Scene", 220),
            ("actions", "Actions", 90),
            ("verify", "Verify", 90),
            ("confirm", "Confirm", 90),
        ):
            self.scene_tree.heading(name, text=heading)
            self.scene_tree.column(
                name,
                width=width,
                anchor="w" if name == "name" else "center",
                stretch=name == "name",
            )
        self.scene_tree.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=8,
            pady=(4, 8),
        )

    def _build_rules_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=3)
        parent.grid_columnconfigure(1, weight=2)
        parent.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(parent, corner_radius=10)
        form.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(8, 5),
        )
        for column in range(7):
            form.grid_columnconfigure(column, weight=1)

        self.rule_name = ctk.CTkEntry(
            form,
            placeholder_text="Rule name",
        )
        self.rule_source = ctk.CTkEntry(
            form,
            placeholder_text="Source entity ID",
        )
        self.rule_condition = ctk.CTkOptionMenu(
            form,
            values=list(RULE_CONDITIONS),
        )
        self.rule_threshold = ctk.CTkEntry(
            form,
            placeholder_text="Threshold",
        )
        self.rule_action = ctk.CTkOptionMenu(
            form,
            values=list(RULE_ACTIONS),
        )
        self.rule_scene = ctk.CTkOptionMenu(
            form,
            values=["No scene"],
        )
        self.rule_cooldown = ctk.CTkEntry(
            form,
            placeholder_text="Cooldown sec",
        )
        for column, widget in enumerate(
            (
                self.rule_name,
                self.rule_source,
                self.rule_condition,
                self.rule_threshold,
                self.rule_action,
                self.rule_scene,
                self.rule_cooldown,
            )
        ):
            widget.grid(row=0, column=column, sticky="ew", padx=3, pady=8)

        ctk.CTkButton(
            form,
            text="Save rule",
            command=self.save_rule,
        ).grid(row=1, column=0, sticky="ew", padx=3, pady=(0, 8))
        ctk.CTkButton(
            form,
            text="Remove rule",
            command=self.remove_rule,
            fg_color=DANGER,
        ).grid(row=1, column=1, sticky="ew", padx=3, pady=(0, 8))
        ctk.CTkButton(
            form,
            text="Evaluate now",
            command=self.evaluate_rules_now,
            fg_color="transparent",
            border_width=1,
        ).grid(row=1, column=2, sticky="ew", padx=3, pady=(0, 8))
        ctk.CTkButton(
            form,
            text="Clear activity",
            command=self.clear_activity,
            fg_color="transparent",
            border_width=1,
        ).grid(row=1, column=3, sticky="ew", padx=3, pady=(0, 8))

        self.rule_tree = ttk.Treeview(
            parent,
            columns=(
                "name",
                "source",
                "condition",
                "action",
                "cooldown",
                "enabled",
            ),
            show="headings",
            selectmode="browse",
        )
        for name, heading, width in (
            ("name", "Rule", 180),
            ("source", "Entity", 85),
            ("condition", "Condition", 140),
            ("action", "Action", 150),
            ("cooldown", "Cooldown", 85),
            ("enabled", "Enabled", 75),
        ):
            self.rule_tree.heading(name, text=heading)
            self.rule_tree.column(
                name,
                width=width,
                anchor="w" if name in {"name", "condition", "action"} else "center",
                stretch=name in {"name", "action"},
            )
        self.rule_tree.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=(8, 4),
            pady=(4, 8),
        )

        self.activity_box = ctk.CTkTextbox(
            parent,
            corner_radius=8,
            wrap="word",
        )
        self.activity_box.grid(
            row=2,
            column=1,
            sticky="nsew",
            padx=(4, 8),
            pady=(4, 8),
        )

    def _settings_changed(self) -> None:
        self.settings = normalize_smart_settings(
            {
                **self.settings,
                "auto_refresh": bool(self.auto_refresh.get()),
                "rules_armed": bool(self.rules_armed.get()),
                "refresh_seconds": safe_int(
                    self.refresh_seconds.get(),
                    5,
                ),
                "verify_scene": bool(self.scene_verify.get())
                if hasattr(self, "scene_verify")
                else self.settings.get("verify_scene", True),
            }
        )
        self.context.store.set(SMART_SETTINGS_KEY, self.settings)
        self._schedule_auto_refresh()

    def _schedule_auto_refresh(self) -> None:
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        if not self.settings.get("auto_refresh", True):
            return
        delay = max(
            3000,
            int(self.settings.get("refresh_seconds", 5)) * 1000,
        )
        self._refresh_job = self.after(delay, self._auto_refresh_tick)

    def _auto_refresh_tick(self) -> None:
        self._refresh_job = None
        if (
            not self._busy
            and self.devices
            and self.context.credentials.is_complete()
        ):
            self._refresh_devices(list(self.devices), automatic=True)
        else:
            self._schedule_auto_refresh()

    def _save_all(self) -> None:
        self.devices = normalize_devices(self.devices)
        ids = self._device_ids()
        self.systems = normalize_systems(self.systems, ids)
        self.scenes = normalize_scenes(self.scenes, ids)
        self.rules = normalize_rules(
            self.rules,
            ids,
            [row["id"] for row in self.scenes],
        )
        self.context.store.set(DEVICE_STORE_KEY, self.devices)
        self.context.store.set(SMART_SYSTEMS_KEY, self.systems)
        self.context.store.set(SMART_SCENES_KEY, self.scenes)
        self.context.store.set(SMART_RULES_KEY, self.rules)
        self.context.store.set(SMART_SETTINGS_KEY, self.settings)
        self.context.store.set(SMART_ACTIVITY_KEY, self.activity)

    def _log(self, message: str, level: str = "info") -> None:
        self.activity = append_activity(
            self.activity,
            message,
            level=level,
            limit=self.settings.get(
                "max_activity",
                DEFAULT_SMART_SETTINGS["max_activity"],
            ),
        )
        self.context.store.set(SMART_ACTIVITY_KEY, self.activity)
        self._render_activity()
        try:
            self.context.record_event(
                "SMART",
                message,
                level,
            )
        except Exception:
            pass

    def _selected_indices(self) -> list[int]:
        children = list(self.device_tree.get_children())
        result: list[int] = []
        for item in self.device_tree.selection():
            try:
                result.append(children.index(item))
            except ValueError:
                continue
        return sorted(set(result))

    def _selected_devices(self) -> list[dict[str, Any]]:
        return [
            self.devices[index]
            for index in self._selected_indices()
            if 0 <= index < len(self.devices)
        ]

    def _selected_system(self) -> dict[str, Any] | None:
        selection = self.system_tree.selection()
        if not selection:
            return None
        index = self.system_tree.index(selection[0])
        return self.systems[index] if index < len(self.systems) else None

    def _selected_scene(self) -> dict[str, Any] | None:
        selection = self.scene_tree.selection()
        if not selection:
            return None
        index = self.scene_tree.index(selection[0])
        return self.scenes[index] if index < len(self.scenes) else None

    def _selected_rule(self) -> dict[str, Any] | None:
        selection = self.rule_tree.selection()
        if not selection:
            return None
        index = self.rule_tree.index(selection[0])
        return self.rules[index] if index < len(self.rules) else None

    def add_device(self) -> None:
        entity_id = safe_int(self.id_entry.get())
        if entity_id <= 0:
            messagebox.showerror(
                "Smart Devices",
                "Enter a valid positive entity ID.",
            )
            return
        if any(int(row["entity_id"]) == entity_id for row in self.devices):
            messagebox.showinfo(
                "Smart Devices",
                "That entity ID is already saved.",
            )
            return
        self.devices.append(
            {
                "entity_id": entity_id,
                "name": self.name_entry.get().strip()
                or f"Entity {entity_id}",
                "zone": self.zone_entry.get().strip()
                or "Main Base",
                "role": self.role_menu.get(),
                "system": self.system_entry.get().strip(),
                "favorite": False,
                "last_status": {},
                "updated_at": "",
            }
        )
        for entry in (
            self.name_entry,
            self.zone_entry,
            self.system_entry,
            self.id_entry,
        ):
            entry.delete(0, "end")
        self._save_all()
        self._log(f"Saved entity {entity_id}.")
        self._render_all()

    def refresh_selected(self) -> None:
        devices = self._selected_devices()
        if not devices:
            self.status.configure(
                text="Select one or more saved devices first."
            )
            return
        self._refresh_devices(devices)

    def refresh_all(self) -> None:
        if not self.devices:
            self.status.configure(text="No smart devices are saved.")
            return
        self._refresh_devices(list(self.devices))

    def _refresh_devices(
        self,
        devices: list[dict[str, Any]],
        *,
        automatic: bool = False,
    ) -> None:
        if self._busy:
            return
        if not self.context.credentials.is_complete():
            self.status.configure(
                text="A complete live Rust+ profile is required."
            )
            self._schedule_auto_refresh()
            return
        ids = [int(row["entity_id"]) for row in devices]
        self._busy = True
        if not automatic:
            self.status.configure(
                text=f"Refreshing {len(ids)} device(s) through one Rust+ session…"
            )

        previous = self._status_map()

        def success(results: dict[int, dict[str, Any]]) -> None:
            self._busy = False
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            for row in self.devices:
                entity_id = int(row["entity_id"])
                if entity_id in results:
                    row["last_status"] = dict(results[entity_id])
                    row["updated_at"] = now
            self._last_refresh_at = time.monotonic()
            self._save_all()
            self._render_all()
            self._evaluate_rules(previous)
            self.status.configure(
                text=f"Updated {len(results)} device(s) at {now[11:19]}."
            )
            self._schedule_auto_refresh()

        def error(exc: Exception) -> None:
            self._busy = False
            self.status.configure(
                text=f"Smart-device refresh failed: {exc}"
            )
            self._log(
                f"Smart-device refresh failed: {exc}",
                "error",
            )
            self._schedule_auto_refresh()

        run_in_worker(
            self,
            lambda: fetch_entities(
                self.context.rust,
                self.context.credentials,
                ids,
            ),
            success,
            error,
        )

    def _set_devices(
        self,
        devices: list[dict[str, Any]],
        value: bool,
        *,
        label: str,
        verify: bool = True,
    ) -> None:
        if not devices or self._busy:
            return
        ids = [int(row["entity_id"]) for row in devices]
        self._busy = True
        state = "ON" if value else "OFF"
        self.status.configure(
            text=f"Sending {state} to {label} ({len(ids)} device(s))…"
        )

        def success(_result: Any) -> None:
            self._busy = False
            self._log(
                f"{label}: {state} command sent to {len(ids)} device(s)."
            )
            if verify:
                self._refresh_devices(devices)
            else:
                self._render_all()
                self._schedule_auto_refresh()

        def error(exc: Exception) -> None:
            self._busy = False
            self.status.configure(
                text=f"Device command failed: {exc}"
            )
            self._log(
                f"{label}: command failed: {exc}",
                "error",
            )
            self._schedule_auto_refresh()

        run_in_worker(
            self,
            lambda: set_entities_value(
                self.context.rust,
                self.context.credentials,
                ids,
                value,
            ),
            success,
            error,
        )

    def set_selected(self, value: bool) -> None:
        devices = self._selected_devices()
        if not devices:
            self.status.configure(
                text="Select one or more devices first."
            )
            return
        self._set_devices(
            devices,
            value,
            label="Selected devices",
        )

    def toggle_favorite(self) -> None:
        selected = self._selected_devices()
        if not selected:
            return
        target = not all(bool(row.get("favorite")) for row in selected)
        ids = {int(row["entity_id"]) for row in selected}
        for row in self.devices:
            if int(row["entity_id"]) in ids:
                row["favorite"] = target
        self._save_all()
        self._render_all()

    def copy_selected_id(self) -> None:
        selected = self._selected_devices()
        if not selected:
            return
        value = ", ".join(str(row["entity_id"]) for row in selected)
        self.clipboard_clear()
        self.clipboard_append(value)
        self.status.configure(text=f"Copied entity ID(s): {value}")

    def remove_selected(self) -> None:
        selected = self._selected_devices()
        if not selected:
            return
        ids = {int(row["entity_id"]) for row in selected}
        if not messagebox.askyesno(
            "Remove smart devices",
            f"Remove {len(ids)} selected device(s) from this profile?",
        ):
            return
        self.devices = [
            row
            for row in self.devices
            if int(row["entity_id"]) not in ids
        ]
        self._save_all()
        self._log(f"Removed {len(ids)} saved device(s).")
        self._render_all()

    def remove_all(self) -> None:
        if not self.devices:
            return
        if not messagebox.askyesno(
            "Remove all smart devices",
            "Remove every saved device, system, scene, and rule?",
        ):
            return
        self.devices = []
        self.systems = []
        self.scenes = []
        self.rules = []
        self._save_all()
        self._log("Removed all saved smart-device automation data.")
        self._render_all()

    def create_system(self) -> None:
        selected = self._selected_devices()
        name = self.system_name.get().strip()
        if not selected or not name:
            messagebox.showerror(
                "Create system",
                "Select devices and enter a system name.",
            )
            return
        self.systems.append(
            {
                "id": str(uuid4()),
                "name": name,
                "zone": self.system_zone.get().strip() or "Main Base",
                "purpose": self.system_purpose.get().strip() or "General",
                "critical": bool(self.system_critical.get()),
                "device_ids": [
                    int(row["entity_id"])
                    for row in selected
                ],
            }
        )
        for row in selected:
            row["system"] = name
        for entry in (
            self.system_name,
            self.system_zone,
            self.system_purpose,
        ):
            entry.delete(0, "end")
        self._save_all()
        self._log(
            f"Created system {name} with {len(selected)} device(s)."
        )
        self._render_all()

    def _system_devices(
        self,
        system: dict[str, Any],
    ) -> list[dict[str, Any]]:
        ids = {int(value) for value in system.get("device_ids") or []}
        return [
            row
            for row in self.devices
            if int(row["entity_id"]) in ids
        ]

    def refresh_selected_system(self) -> None:
        system = self._selected_system()
        if system is None:
            return
        self._refresh_devices(self._system_devices(system))

    def set_selected_system(self, value: bool) -> None:
        system = self._selected_system()
        if system is None:
            return
        self._set_devices(
            self._system_devices(system),
            value,
            label=str(system.get("name") or "System"),
        )

    def scene_from_system(self, value: bool) -> None:
        system = self._selected_system()
        if system is None:
            return
        name = f"{system['name']} {'ON' if value else 'OFF'}"
        self.scenes.append(
            {
                "id": str(uuid4()),
                "name": name,
                "description": f"Generated from system {system['name']}.",
                "actions": [
                    {
                        "entity_id": int(entity_id),
                        "value": bool(value),
                    }
                    for entity_id in system.get("device_ids") or []
                ],
                "verify": True,
                "confirm": True,
                "favorite": False,
            }
        )
        self._save_all()
        self._log(f"Created scene {name}.")
        self._render_all()

    def remove_system(self) -> None:
        system = self._selected_system()
        if system is None:
            return
        self.systems = [
            row
            for row in self.systems
            if row.get("id") != system.get("id")
        ]
        self._save_all()
        self._log(f"Removed system {system['name']}.")
        self._render_all()

    def create_scene_from_selected(self, value: bool) -> None:
        selected = self._selected_devices()
        name = self.scene_name.get().strip()
        if not selected or not name:
            messagebox.showerror(
                "Create scene",
                "Select devices on the Devices tab and enter a scene name.",
            )
            return
        self.scenes.append(
            {
                "id": str(uuid4()),
                "name": name,
                "description": "Created from selected devices.",
                "actions": [
                    {
                        "entity_id": int(row["entity_id"]),
                        "value": bool(value),
                    }
                    for row in selected
                ],
                "verify": bool(self.scene_verify.get()),
                "confirm": bool(self.scene_confirm.get()),
                "favorite": False,
            }
        )
        self.scene_name.delete(0, "end")
        self._save_all()
        self._log(
            f"Created scene {name} with {len(selected)} action(s)."
        )
        self._render_all()

    def capture_scene_from_status(self) -> None:
        selected = self._selected_devices()
        if not selected:
            return
        actions = []
        for row in selected:
            value = status_value(row.get("last_status") or {})
            if value is None:
                continue
            actions.append(
                {
                    "entity_id": int(row["entity_id"]),
                    "value": value,
                }
            )
        if not actions:
            messagebox.showinfo(
                "Capture scene",
                "Refresh selected devices first; none have a readable ON/OFF value.",
            )
            return
        name = f"Captured {datetime.now().strftime('%H:%M:%S')}"
        self.scenes.append(
            {
                "id": str(uuid4()),
                "name": name,
                "description": "Captured from current device values.",
                "actions": actions,
                "verify": True,
                "confirm": True,
                "favorite": False,
            }
        )
        self._save_all()
        self._log(f"Captured current values as scene {name}.")
        self._render_all()

    def preview_selected_scene(self) -> None:
        scene = self._selected_scene()
        if scene is None:
            return
        names = {
            int(row["entity_id"]): str(row["name"])
            for row in self.devices
        }
        lines = [f"SCENE: {scene['name']}", ""]
        for action in scene_plan(scene, self._status_map()):
            state = "ON" if action["value"] else "OFF"
            suffix = " (already set)" if action["already_set"] else ""
            lines.append(
                f"- {names.get(action['entity_id'], action['entity_id'])}: "
                f"{state}{suffix}"
            )
        messagebox.showinfo(
            "Scene preview",
            "\n".join(lines),
        )

    def run_selected_scene(self) -> None:
        scene = self._selected_scene()
        if scene is None:
            return
        self._run_scene(scene, automatic=False)

    def _run_scene(
        self,
        scene: dict[str, Any],
        *,
        automatic: bool,
    ) -> None:
        plan = scene_plan(scene, self._status_map())
        if not plan:
            return
        if (
            scene.get("confirm", True)
            and not automatic
            and not messagebox.askyesno(
                "Run scene",
                f"Run {scene['name']} with {len(plan)} action(s)?",
            )
        ):
            return

        on_ids = [
            int(row["entity_id"])
            for row in plan
            if row["value"] and not row["already_set"]
        ]
        off_ids = [
            int(row["entity_id"])
            for row in plan
            if not row["value"] and not row["already_set"]
        ]
        if not on_ids and not off_ids:
            self.status.configure(
                text=f"{scene['name']} is already in the requested state."
            )
            return
        if self._busy:
            return
        self._busy = True
        self.status.configure(text=f"Running scene {scene['name']}…")

        def work():
            result: dict[str, Any] = {}
            if on_ids:
                result["on"] = set_entities_value(
                    self.context.rust,
                    self.context.credentials,
                    on_ids,
                    True,
                )
            if off_ids:
                result["off"] = set_entities_value(
                    self.context.rust,
                    self.context.credentials,
                    off_ids,
                    False,
                )
            return result

        def success(_result: Any) -> None:
            self._busy = False
            self._log(
                f"Scene {scene['name']} executed: "
                f"{len(on_ids)} ON, {len(off_ids)} OFF."
            )
            if scene.get("verify", True):
                devices = [
                    row
                    for row in self.devices
                    if int(row["entity_id"]) in set(on_ids + off_ids)
                ]
                self._refresh_devices(devices)
            else:
                self._render_all()
                self._schedule_auto_refresh()

        def error(exc: Exception) -> None:
            self._busy = False
            self._log(
                f"Scene {scene['name']} failed: {exc}",
                "error",
            )
            self.status.configure(
                text=f"Scene failed: {exc}"
            )
            self._schedule_auto_refresh()

        run_in_worker(self, work, success, error)

    def favorite_scene(self) -> None:
        scene = self._selected_scene()
        if scene is None:
            return
        scene["favorite"] = not bool(scene.get("favorite"))
        self._save_all()
        self._render_all()

    def duplicate_scene(self) -> None:
        scene = self._selected_scene()
        if scene is None:
            return
        copy = dict(scene)
        copy["id"] = str(uuid4())
        copy["name"] = f"{scene['name']} Copy"
        copy["actions"] = [
            dict(action)
            for action in scene.get("actions") or []
        ]
        self.scenes.append(copy)
        self._save_all()
        self._render_all()

    def remove_scene(self) -> None:
        scene = self._selected_scene()
        if scene is None:
            return
        self.scenes = [
            row
            for row in self.scenes
            if row.get("id") != scene.get("id")
        ]
        self._save_all()
        self._log(f"Removed scene {scene['name']}.")
        self._render_all()

    def _scene_name_to_id(self) -> dict[str, str]:
        return {
            str(row["name"]): str(row["id"])
            for row in self.scenes
        }

    def save_rule(self) -> None:
        source = safe_int(self.rule_source.get())
        if source not in self._device_ids():
            messagebox.showerror(
                "Save rule",
                "Enter the entity ID of a saved device.",
            )
            return
        scene_map = self._scene_name_to_id()
        selected_scene = self.rule_scene.get()
        scene_id = scene_map.get(selected_scene, "")
        action = self.rule_action.get()
        if action in {"Run scene", "Notify and run scene"} and not scene_id:
            messagebox.showerror(
                "Save rule",
                "Choose a scene for this rule action.",
            )
            return
        self.rules.append(
            {
                "id": str(uuid4()),
                "name": self.rule_name.get().strip()
                or f"{self.rule_condition.get()} on {source}",
                "source_entity_id": source,
                "condition": self.rule_condition.get(),
                "threshold": safe_int(self.rule_threshold.get(), 25),
                "action": action,
                "scene_id": scene_id,
                "cooldown_seconds": safe_int(
                    self.rule_cooldown.get(),
                    60,
                ),
                "enabled": True,
                "last_triggered_at": "",
            }
        )
        for entry in (
            self.rule_name,
            self.rule_source,
            self.rule_threshold,
            self.rule_cooldown,
        ):
            entry.delete(0, "end")
        self._save_all()
        self._log("Saved smart-device automation rule.")
        self._render_all()

    def remove_rule(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            return
        self.rules = [
            row
            for row in self.rules
            if row.get("id") != rule.get("id")
        ]
        self._save_all()
        self._log(f"Removed rule {rule['name']}.")
        self._render_all()

    def evaluate_rules_now(self) -> None:
        self._evaluate_rules(
            self._previous_statuses,
            manual=True,
        )

    def _evaluate_rules(
        self,
        previous_statuses: dict[int, dict[str, Any]],
        *,
        manual: bool = False,
    ) -> None:
        current = self._status_map()
        triggered, updated = evaluate_rules(
            self.rules,
            current,
            previous_statuses,
        )
        self.rules = updated
        self._previous_statuses = current
        self._save_all()

        if not triggered:
            if manual:
                self.status.configure(
                    text="No enabled rule condition is currently triggered."
                )
            self._render_rules()
            return

        names = {
            int(row["entity_id"]): str(row["name"])
            for row in self.devices
        }
        scene_by_id = {
            str(row["id"]): row
            for row in self.scenes
        }
        alerts: list[DealAlert] = []
        for rule in triggered:
            source = int(rule["source_entity_id"])
            message = (
                f"{rule['name']} triggered by "
                f"{names.get(source, source)}."
            )
            self._log(message, "warning")
            alerts.append(
                DealAlert(
                    fingerprint=f"smart-rule:{rule['id']}:{rule['last_triggered_at']}",
                    severity=3,
                    title="Smart base rule triggered",
                    message=message,
                    label="SMART DEVICE",
                    score=100,
                    grid="",
                    shop="Smart Devices",
                    item_name=names.get(source, str(source)),
                )
            )

            if (
                self.settings.get("rules_armed", False)
                and rule.get("action")
                in {"Run scene", "Notify and run scene"}
            ):
                scene = scene_by_id.get(str(rule.get("scene_id") or ""))
                if scene is not None:
                    self._run_scene(scene, automatic=True)

        app = getattr(self.context, "app", None)
        publish = getattr(app, "publish_device_alerts", None)
        if alerts and callable(publish):
            publish(alerts)
        self._render_rules()

    def clear_activity(self) -> None:
        self.activity = []
        self.context.store.set(SMART_ACTIVITY_KEY, [])
        self._render_activity()

    def _render_all(self) -> None:
        self._render_devices()
        self._render_systems()
        self._render_scenes()
        self._render_rules()
        self._render_activity()
        self._render_metrics()

    def _render_devices(self) -> None:
        selected_ids = {
            int(row["entity_id"])
            for row in self._selected_devices()
        } if hasattr(self, "device_tree") else set()
        self.device_tree.delete(*self.device_tree.get_children())
        for row in self.devices:
            status = row.get("last_status") or {}
            value = status_value(status)
            state = (
                "ERROR"
                if status.get("error")
                else "ON"
                if value is True
                else "OFF"
                if value is False
                else "—"
            )
            capacity = status_capacity(status)
            checked = str(row.get("updated_at") or "")
            item = self.device_tree.insert(
                "",
                "end",
                values=(
                    ("★ " if row.get("favorite") else "") + str(row["name"]),
                    row["zone"],
                    row["role"],
                    row["system"],
                    row["entity_id"],
                    state,
                    "—" if capacity is None else f"{capacity:g}",
                    checked[11:19] if len(checked) >= 19 else "Never",
                ),
            )
            if int(row["entity_id"]) in selected_ids:
                self.device_tree.selection_add(item)

    def _render_systems(self) -> None:
        self.system_tree.delete(*self.system_tree.get_children())
        statuses = self._status_map()
        for row in self.systems:
            summary = system_summary(row, statuses)
            self.system_tree.insert(
                "",
                "end",
                values=(
                    ("★ " if row.get("critical") else "") + row["name"],
                    row["zone"],
                    row["purpose"],
                    summary["count"],
                    summary["online"],
                    summary["on"],
                    summary["errors"],
                ),
            )

    def _render_scenes(self) -> None:
        self.scene_tree.delete(*self.scene_tree.get_children())
        for row in self.scenes:
            self.scene_tree.insert(
                "",
                "end",
                values=(
                    ("★ " if row.get("favorite") else "") + row["name"],
                    len(row.get("actions") or []),
                    "Yes" if row.get("verify") else "No",
                    "Yes" if row.get("confirm") else "No",
                ),
            )
        values = ["No scene"] + [str(row["name"]) for row in self.scenes]
        self.rule_scene.configure(values=values)
        if self.rule_scene.get() not in values:
            self.rule_scene.set(values[0])

    def _render_rules(self) -> None:
        self.rule_tree.delete(*self.rule_tree.get_children())
        scene_by_id = {
            str(row["id"]): str(row["name"])
            for row in self.scenes
        }
        for row in self.rules:
            action = str(row["action"])
            if row.get("scene_id"):
                action += f" → {scene_by_id.get(str(row['scene_id']), 'Missing scene')}"
            self.rule_tree.insert(
                "",
                "end",
                values=(
                    row["name"],
                    row["source_entity_id"],
                    row["condition"],
                    action,
                    f"{row['cooldown_seconds']}s",
                    "Yes" if row.get("enabled") else "No",
                ),
            )

    def _render_activity(self) -> None:
        if not hasattr(self, "activity_box"):
            return
        lines = []
        for row in self.activity[-100:]:
            time_text = str(row.get("time") or "")
            lines.append(
                f"[{time_text[11:19] if len(time_text) >= 19 else time_text}] "
                f"{str(row.get('level') or 'info').upper()} · "
                f"{row.get('message') or ''}"
            )
        self.activity_box.configure(state="normal")
        self.activity_box.delete("1.0", "end")
        self.activity_box.insert(
            "1.0",
            "\n".join(lines) or "No smart-device activity yet.",
        )
        self.activity_box.configure(state="disabled")

    def _render_metrics(self) -> None:
        statuses = self._status_map()
        on_count = sum(
            status_value(status) is True
            for status in statuses.values()
        )
        armed = sum(
            bool(row.get("enabled"))
            for row in self.rules
        ) if self.settings.get("rules_armed") else 0
        self.saved_metric.configure(
            text=f"SAVED\n{len(self.devices)}"
        )
        self.on_metric.configure(text=f"ON\n{on_count}")
        self.system_metric.configure(
            text=f"SYSTEMS\n{len(self.systems)}"
        )
        self.scene_metric.configure(
            text=f"SCENES\n{len(self.scenes)}"
        )
        self.rule_metric.configure(
            text=f"RULES ARMED\n{armed}"
        )
        if self.context.rustplus_live:
            self.live_badge.configure(
                text="  LIVE  ",
                text_color=SUCCESS,
            )
        else:
            self.live_badge.configure(
                text="  OFFLINE  ",
                text_color=MUTED,
            )

    def _show_selected_detail(self) -> None:
        selected = self._selected_devices()
        lines: list[str] = []
        for row in selected[:8]:
            status = row.get("last_status") or {}
            lines.extend(
                (
                    f"{row['name']} · {row['zone']}",
                    f"Entity ID: {row['entity_id']}",
                    f"Role: {row['role']}",
                    f"System: {row['system'] or 'None'}",
                    f"Type: {status.get('type', '—')}",
                    f"Value: {status.get('value', '—')}",
                    f"Capacity: {status.get('capacity', '—')}",
                    f"Protection: {status.get('has_protection', '—')}",
                    f"Protection expiry: {status.get('protection_expiry', '—')}",
                    f"Error: {status.get('error', 'None')}",
                    "",
                )
            )
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert(
            "1.0",
            "\n".join(lines).rstrip()
            or "Select one or more devices.",
        )
        self.detail.configure(state="disabled")

    def on_context_updated(self) -> None:
        self._render_metrics()
        if (
            self.settings.get("auto_refresh", True)
            and time.monotonic() - self._last_refresh_at
            >= self.settings.get("refresh_seconds", 5)
            and not self._busy
            and self.devices
            and self.context.credentials.is_complete()
        ):
            self._refresh_devices(
                list(self.devices),
                automatic=True,
            )
