from __future__ import annotations

from datetime import datetime, timezone
from tkinter import messagebox, ttk

import customtkinter as ctk

from rust_companion_plus.services.profile_retention import (
    PROFILE_RETENTION_DAYS,
    delete_all_saved_profiles,
    delete_saved_profile,
    profile_activity_time,
    purge_expired_profiles,
)
from rust_companion_plus.ui.common import DANGER, MUTED


class SavedServersTab(ctk.CTkFrame):
    """Visible management for the 30-day saved-server retention policy."""

    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self._profiles: list[dict] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Saved Servers",
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header,
            text=(
                f"Saved server profiles expire automatically after {PROFILE_RETENTION_DAYS} days "
                "without a live update. Remove one profile or clear the entire vault here."
            ),
            text_color=MUTED,
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        actions.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            actions,
            text="Refresh list",
            width=110,
            fg_color="transparent",
            border_width=1,
            command=self.refresh,
        ).grid(row=0, column=1, padx=4)
        ctk.CTkButton(
            actions,
            text="Remove selected",
            width=140,
            fg_color=DANGER,
            command=self.remove_selected,
        ).grid(row=0, column=2, padx=4)
        ctk.CTkButton(
            actions,
            text="Remove all saved servers",
            width=180,
            fg_color=DANGER,
            command=self.remove_all,
        ).grid(row=0, column=3, padx=(4, 0))

        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=2, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            card,
            columns=("name", "game", "rustplus", "map", "updated", "expires", "active"),
            show="headings",
            selectmode="browse",
        )
        settings = (
            ("name", "Server", 220, "w"),
            ("game", "Game endpoint", 140, "center"),
            ("rustplus", "Rust+ endpoint", 140, "center"),
            ("map", "Map", 135, "center"),
            ("updated", "Last live/save", 150, "center"),
            ("expires", "Expires in", 90, "center"),
            ("active", "Current", 72, "center"),
        )
        for name, heading, width, anchor in settings:
            self.tree.heading(name, text=heading)
            self.tree.column(name, width=width, anchor=anchor, stretch=name == "name")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=12, padx=(0, 12))
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.status = ctk.CTkLabel(
            self,
            text="",
            text_color=MUTED,
            anchor="w",
        )
        self.status.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        purge_expired_profiles(self.context.store)
        self.refresh()

    def _vault(self):
        return self.context.profile_vault

    def _selected_profile(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        children = list(self.tree.get_children())
        try:
            index = children.index(selection[0])
        except ValueError:
            return None
        if not 0 <= index < len(self._profiles):
            return None
        return self._profiles[index]

    @staticmethod
    def _expiry_text(record: dict) -> str:
        activity = profile_activity_time(record)
        if activity is None:
            return "Unknown"
        now = datetime.now(timezone.utc)
        remaining = PROFILE_RETENTION_DAYS - (now - activity).days
        if remaining <= 0:
            return "Due now"
        return f"{remaining} day{'s' if remaining != 1 else ''}"

    def refresh(self) -> None:
        vault = self._vault()
        self._profiles = vault.list_profiles() if vault is not None else []
        self.tree.delete(*self.tree.get_children())
        active_key = str(self.context.active_profile_key or "")
        for record in self._profiles:
            summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
            updated = str(
                record.get("live_updated_at")
                or record.get("saved_at")
                or ""
            ).replace("T", " ")[:19]
            key = str(record.get("key") or "")
            self.tree.insert(
                "",
                "end",
                values=(
                    record.get("name") or key or "Unnamed",
                    record.get("game_endpoint") or key or "—",
                    record.get("rustplus_endpoint") or "—",
                    summary.get("map") or "—",
                    updated or "Unknown",
                    self._expiry_text(record),
                    "Yes" if key == active_key else "",
                ),
            )
        cleanup = self.context.store.get("saved_server_profile_cleanup", {}) or {}
        last_check = str(cleanup.get("checked_at") or "").replace("T", " ")[:19]
        self.status.configure(
            text=(
                f"{len(self._profiles)} saved server profile(s). "
                f"Automatic {PROFILE_RETENTION_DAYS}-day cleanup last checked: {last_check or 'this launch'}."
            )
        )

    def remove_selected(self) -> None:
        record = self._selected_profile()
        if record is None:
            self.status.configure(text="Select one saved server first.")
            return
        key = str(record.get("key") or "")
        name = str(record.get("name") or key)
        if not messagebox.askyesno(
            "Remove saved server?",
            f"Remove {name} and its cached map/workspace data?\n\nThis cannot be undone.",
        ):
            return
        if delete_saved_profile(self.context.store, key):
            if key == self.context.active_profile_key:
                self.context.active_profile_key = ""
                self.context.profile_record = {}
            self.status.configure(text=f"Removed saved server: {name}")
            self.refresh()
        else:
            self.status.configure(text="That saved server no longer exists.")

    def remove_all(self) -> None:
        if not self._profiles:
            return
        if not messagebox.askyesno(
            "Remove all saved servers?",
            (
                f"Remove all {len(self._profiles)} saved server profiles, cached maps, and "
                "server-specific workspaces?\n\nThis cannot be undone."
            ),
        ):
            return
        removed = delete_all_saved_profiles(self.context.store)
        self.context.active_profile_key = ""
        self.context.profile_record = {}
        self.refresh()
        self.status.configure(text=f"Removed {len(removed)} saved server profile(s).")

    def on_context_updated(self) -> None:
        self.refresh()
