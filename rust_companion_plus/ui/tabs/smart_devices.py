from __future__ import annotations

import time
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any

import customtkinter as ctk

from rust_companion_plus.services.rustplus_entities import fetch_entities, set_entities_value
from rust_companion_plus.ui.common import DANGER, MUTED, SUCCESS, run_in_worker, safe_int


DEVICE_STORE_KEY = "smart_devices"
AUTO_REFRESH_SECONDS = 15.0


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
            str(row.get("zone", "")).casefold(),
            str(row.get("name", "")).casefold(),
        )
    )
    return rows


class SmartDevicesTab(ctk.CTkFrame):
    """Saved Rust+ smart-device hub with batch status and control."""

    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.devices = normalize_devices(context.store.get(DEVICE_STORE_KEY, []))
        self._busy = False
        self._last_auto_refresh = 0.0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Smart Devices",
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header,
            text=(
                "Save paired entity IDs, read every Rust+ status field, and control "
                "one device or an entire selected group."
            ),
            text_color=MUTED,
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.live_badge = ctk.CTkLabel(
            header,
            text="  OFFLINE  ",
            text_color=MUTED,
            corner_radius=999,
            fg_color=("#e5e7eb", "#111827"),
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.live_badge.grid(row=0, column=1, rowspan=2, padx=(10, 0))

        metrics = ctk.CTkFrame(self, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        for column in range(3):
            metrics.grid_columnconfigure(column, weight=1)
        self.saved_metric = self._metric(metrics, 0, "Saved", "0")
        self.on_metric = self._metric(metrics, 1, "On", "0")
        self.protected_metric = self._metric(metrics, 2, "Protected", "0")

        add_card = ctk.CTkFrame(self, corner_radius=12)
        add_card.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        add_card.grid_columnconfigure((0, 1, 2), weight=1)
        self.name_entry = ctk.CTkEntry(add_card, placeholder_text="Device name")
        self.zone_entry = ctk.CTkEntry(add_card, placeholder_text="Zone / room")
        self.id_entry = ctk.CTkEntry(add_card, placeholder_text="Paired entity ID")
        for column, entry in enumerate((self.name_entry, self.zone_entry, self.id_entry)):
            entry.grid(row=0, column=column, sticky="ew", padx=6, pady=12)
        ctk.CTkButton(
            add_card,
            text="Save device",
            width=120,
            command=self.add_device,
        ).grid(row=0, column=3, padx=(6, 12), pady=12)

        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=3, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        for column in range(8):
            actions.grid_columnconfigure(column, weight=1)
        buttons = (
            ("Refresh selected", self.refresh_selected, None),
            ("Refresh all", self.refresh_all, None),
            ("Turn ON", lambda: self.set_selected(True), None),
            ("Turn OFF", lambda: self.set_selected(False), "outline"),
            ("Favorite", self.toggle_favorite, "outline"),
            ("Copy ID", self.copy_selected_id, "outline"),
            ("Remove", self.remove_selected, "danger"),
            ("Remove all", self.remove_all, "danger"),
        )
        for column, (text, command, style) in enumerate(buttons):
            kwargs: dict[str, Any] = {}
            if style == "outline":
                kwargs.update(fg_color="transparent", border_width=1)
            elif style == "danger":
                kwargs.update(fg_color=DANGER)
            ctk.CTkButton(
                actions,
                text=text,
                command=command,
                height=34,
                **kwargs,
            ).grid(row=0, column=column, sticky="ew", padx=3)

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            body,
            columns=("name", "zone", "id", "type", "state", "capacity", "checked"),
            show="headings",
            selectmode="extended",
        )
        settings = (
            ("name", "Name", 170, "w"),
            ("zone", "Zone", 120, "w"),
            ("id", "Entity ID", 100, "center"),
            ("type", "Type", 105, "center"),
            ("state", "State", 75, "center"),
            ("capacity", "Capacity", 85, "center"),
            ("checked", "Last check", 135, "center"),
        )
        for name, heading, width, anchor in settings:
            self.tree.heading(name, text=heading)
            self.tree.column(name, width=width, anchor=anchor, stretch=name in {"name", "zone"})
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected_detail())

        self.detail = ctk.CTkTextbox(body, corner_radius=8, wrap="word")
        self.detail.grid(row=0, column=1, sticky="nsew")
        self.status = ctk.CTkLabel(
            self,
            text="Add a paired entity ID to begin.",
            text_color=MUTED,
            anchor="w",
        )
        self.status.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self._render()

    @staticmethod
    def _metric(parent, column: int, title: str, value: str):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.grid(row=0, column=column, sticky="ew", padx=4)
        label = ctk.CTkLabel(
            card,
            text=f"{title.upper()}\n{value}",
            font=ctk.CTkFont(size=15, weight="bold"),
            justify="left",
            anchor="w",
        )
        label.pack(fill="x", padx=12, pady=10)
        return label

    def _save(self) -> None:
        self.context.store.set(DEVICE_STORE_KEY, self.devices)

    def _selected_indices(self) -> list[int]:
        indices: list[int] = []
        children = list(self.tree.get_children())
        for item in self.tree.selection():
            try:
                indices.append(children.index(item))
            except ValueError:
                continue
        return sorted(set(indices))

    def _selected_devices(self) -> list[dict[str, Any]]:
        return [
            self.devices[index]
            for index in self._selected_indices()
            if 0 <= index < len(self.devices)
        ]

    def add_device(self) -> None:
        entity_id = safe_int(self.id_entry.get())
        if entity_id <= 0:
            messagebox.showerror("Smart Devices", "Enter a valid positive entity ID.")
            return
        if any(int(row["entity_id"]) == entity_id for row in self.devices):
            messagebox.showinfo("Smart Devices", "That entity ID is already saved.")
            return
        self.devices.append(
            {
                "entity_id": entity_id,
                "name": self.name_entry.get().strip() or f"Entity {entity_id}",
                "zone": self.zone_entry.get().strip() or "Main Base",
                "favorite": False,
                "last_status": {},
                "updated_at": "",
            }
        )
        self.devices = normalize_devices(self.devices)
        self._save()
        for entry in (self.name_entry, self.zone_entry, self.id_entry):
            entry.delete(0, "end")
        self._render()
        self.status.configure(text=f"Saved entity {entity_id}. Refresh to verify it through Rust+.")

    def refresh_selected(self) -> None:
        devices = self._selected_devices()
        if not devices:
            self.status.configure(text="Select one or more saved devices first.")
            return
        self._refresh_devices(devices)

    def refresh_all(self) -> None:
        if not self.devices:
            self.status.configure(text="No smart devices are saved.")
            return
        self._refresh_devices(list(self.devices))

    def _refresh_devices(self, devices: list[dict[str, Any]]) -> None:
        if self._busy:
            return
        if not self.context.credentials.is_complete():
            self.status.configure(text="A complete live Rust+ profile is required.")
            return
        ids = [int(row["entity_id"]) for row in devices]
        self._busy = True
        self.status.configure(text=f"Refreshing {len(ids)} device(s) through one Rust+ session…")

        def success(results: dict[int, dict[str, Any]]) -> None:
            self._busy = False
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            for row in self.devices:
                entity_id = int(row["entity_id"])
                if entity_id in results:
                    row["last_status"] = dict(results[entity_id])
                    row["updated_at"] = now
            self._save()
            self._last_auto_refresh = time.monotonic()
            self._render()
            self.status.configure(text=f"Updated {len(results)} smart device(s) at {now[11:19]}.")

        def error(exc: Exception) -> None:
            self._busy = False
            self.status.configure(text=f"Smart-device refresh failed: {exc}")

        run_in_worker(
            self,
            lambda: fetch_entities(self.context.rust, self.context.credentials, ids),
            success,
            error,
        )

    def set_selected(self, value: bool) -> None:
        devices = self._selected_devices()
        if not devices:
            self.status.configure(text="Select one or more saved devices first.")
            return
        if self._busy:
            return
        ids = [int(row["entity_id"]) for row in devices]
        self._busy = True
        state = "ON" if value else "OFF"
        self.status.configure(text=f"Sending {state} to {len(ids)} device(s)…")

        def success(_result: Any) -> None:
            self._busy = False
            self.status.configure(text=f"{state} command sent. Refreshing status…")
            self._refresh_devices(devices)

        def error(exc: Exception) -> None:
            self._busy = False
            self.status.configure(text=f"Device command failed: {exc}")

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

    def toggle_favorite(self) -> None:
        devices = self._selected_devices()
        if not devices:
            return
        for row in devices:
            row["favorite"] = not bool(row.get("favorite"))
        self.devices = normalize_devices(self.devices)
        self._save()
        self._render()

    def copy_selected_id(self) -> None:
        devices = self._selected_devices()
        if len(devices) != 1:
            self.status.configure(text="Select exactly one device to copy its ID.")
            return
        value = str(devices[0]["entity_id"])
        self.clipboard_clear()
        self.clipboard_append(value)
        self.status.configure(text=f"Copied entity ID {value}.")

    def remove_selected(self) -> None:
        indices = self._selected_indices()
        if not indices:
            return
        if not messagebox.askyesno("Remove smart devices", f"Remove {len(indices)} selected device(s)?"):
            return
        remove = set(indices)
        self.devices = [row for index, row in enumerate(self.devices) if index not in remove]
        self._save()
        self._render()

    def remove_all(self) -> None:
        if not self.devices:
            return
        if not messagebox.askyesno("Remove all smart devices", "Remove every saved smart device from this server profile?"):
            return
        self.devices = []
        self._save()
        self._render()

    def _render(self) -> None:
        selected_ids = {
            int(row["entity_id"])
            for row in self._selected_devices()
        }
        self.tree.delete(*self.tree.get_children())
        on_count = 0
        protected_count = 0
        for row in self.devices:
            status = dict(row.get("last_status") or {})
            value = status.get("value")
            is_on = bool(value)
            on_count += int(is_on)
            protected_count += int(bool(status.get("has_protection")))
            prefix = "★ " if row.get("favorite") else ""
            item = self.tree.insert(
                "",
                "end",
                values=(
                    prefix + str(row.get("name") or "Unnamed"),
                    row.get("zone") or "Main Base",
                    row["entity_id"],
                    status.get("type") or "Unknown",
                    "ON" if is_on else "OFF" if value is not None else "—",
                    status.get("capacity") if status.get("capacity") is not None else "—",
                    str(row.get("updated_at") or "").replace("T", " ")[:19] or "Never",
                ),
            )
            if int(row["entity_id"]) in selected_ids:
                self.tree.selection_add(item)
        self.saved_metric.configure(text=f"SAVED\n{len(self.devices)}")
        self.on_metric.configure(text=f"ON\n{on_count}")
        self.protected_metric.configure(text=f"PROTECTED\n{protected_count}")
        live = bool(self.context.credentials.is_complete())
        self.live_badge.configure(
            text="  RUST+ READY  " if live else "  OFFLINE  ",
            text_color=SUCCESS if live else MUTED,
        )
        self._show_selected_detail()

    def _show_selected_detail(self) -> None:
        devices = self._selected_devices()
        if not devices:
            text = (
                "Select a device to inspect every status field returned by Rust+.\n\n"
                "Smart switches and compatible paired entities can be read and toggled. "
                "Protection, capacity, and expiry fields are shown when the server exposes them."
            )
        elif len(devices) > 1:
            text = f"{len(devices)} devices selected. Batch refresh and ON/OFF actions apply to all of them."
        else:
            row = devices[0]
            status = dict(row.get("last_status") or {})
            lines = [
                str(row.get("name") or "Unnamed device"),
                f"Zone: {row.get('zone') or 'Main Base'}",
                f"Entity ID: {row['entity_id']}",
                f"Favorite: {'Yes' if row.get('favorite') else 'No'}",
                f"Last check: {row.get('updated_at') or 'Never'}",
                "",
                "RUST+ STATUS",
            ]
            if status:
                lines.extend(f"{key}: {value}" for key, value in sorted(status.items()))
            else:
                lines.append("No status has been read yet.")
            text = "\n".join(lines)
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)

    def on_context_updated(self) -> None:
        self.devices = normalize_devices(self.context.store.get(DEVICE_STORE_KEY, []))
        self._render()
        if (
            self.devices
            and not self._busy
            and self.context.credentials.is_complete()
            and time.monotonic() - self._last_auto_refresh >= AUTO_REFRESH_SECONDS
        ):
            self.refresh_all()
