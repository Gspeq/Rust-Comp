from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from rust_companion_plus.models import RustCredentials
from rust_companion_plus.ui.common import MetricCard, SectionCard, run_in_worker, safe_int


class DashboardTab(ctk.CTkScrollableFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            self,
            text="Server Overview",
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 12))

        self.metrics = {}
        for column, key, title in [
            (0, "name", "Server"),
            (1, "players", "Players"),
            (2, "map", "Map"),
            (3, "time", "Server Time"),
        ]:
            card = MetricCard(self, title)
            card.grid(row=1, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0), pady=(0, 12))
            self.metrics[key] = card

        card = SectionCard(
            self,
            "Rust+ Connection",
            "Enter the values produced by your Rust+ pairing/link workflow. "
            "The token field is masked and never printed.",
        )
        card.grid(row=2, column=0, columnspan=4, sticky="ew", pady=8)
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.grid(row=card.content_row, column=0, sticky="ew", padx=14, pady=(0, 14))
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)

        creds = context.credentials
        self.host = ctk.CTkEntry(form, placeholder_text="Server IP / host")
        self.host.insert(0, creds.host)
        self.host.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self.port = ctk.CTkEntry(form, placeholder_text="Companion port")
        if creds.port:
            self.port.insert(0, str(creds.port))
        self.port.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        self.steam = ctk.CTkEntry(form, placeholder_text="Steam ID")
        if creds.steam_id:
            self.steam.insert(0, str(creds.steam_id))
        self.steam.grid(row=0, column=2, sticky="ew", padx=4, pady=4)
        self.token = ctk.CTkEntry(form, placeholder_text="Player token", show="•")
        if creds.player_token:
            self.token.insert(0, str(creds.player_token))
        self.token.grid(row=0, column=3, sticky="ew", padx=4, pady=4)

        ctk.CTkButton(form, text="Save credentials", command=self.save_credentials).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=6
        )
        self.connect_button = ctk.CTkButton(
            form, text="Connect and refresh", command=self.connect
        )
        self.connect_button.grid(row=1, column=2, columnspan=2, sticky="ew", padx=4, pady=6)

        events = SectionCard(self, "Active map events", "Markers supplied by the connected Rust server.")
        events.grid(row=3, column=0, columnspan=4, sticky="ew", pady=8)
        self.events_box = ctk.CTkTextbox(events, height=180)
        self.events_box.grid(row=events.content_row, column=0, sticky="ew", padx=14, pady=(0, 14))
        self.events_box.insert("1.0", "Connect to a server to load event markers.")
        self.events_box.configure(state="disabled")

    def save_credentials(self) -> None:
        credentials = RustCredentials(
            host=self.host.get().strip(),
            port=safe_int(self.port.get()),
            steam_id=safe_int(self.steam.get()),
            player_token=safe_int(self.token.get()),
        )
        self.context.credentials = credentials
        self.context.store.set("credentials", credentials.to_dict())
        messagebox.showinfo("Rust Companion+", "Credentials saved locally.")

    def connect(self) -> None:
        self.save_credentials()
        self.connect_button.configure(state="disabled", text="Connecting…")

        def success(snapshot):
            self.connect_button.configure(state="normal", text="Connect and refresh")
            self.context.snapshot = snapshot
            self.context.notify_data_changed()
            self.refresh()

        def error(exc):
            self.connect_button.configure(state="normal", text="Connect and refresh")
            messagebox.showerror("Rust+ connection failed", str(exc))

        run_in_worker(
            self,
            lambda: self.context.rust.fetch_snapshot(self.context.credentials),
            success,
            error,
        )

    def refresh(self) -> None:
        snapshot = self.context.snapshot
        if snapshot is None:
            return
        server = snapshot.server
        self.metrics["name"].set(str(server.get("name") or "Unknown"), str(server.get("url") or ""))
        self.metrics["players"].set(
            f"{server.get('players', 0)}/{server.get('max_players', 0)}",
            f"Queue: {server.get('queued_players', 0)}",
        )
        self.metrics["map"].set(
            str(server.get("map") or "Procedural"),
            f"Seed {server.get('seed', '—')} · Size {server.get('size') or server.get('map_size') or '—'}",
        )
        self.metrics["time"].set(snapshot.server_time or "—", "Live Rust+ value")

        event_types = {4: "Chinook / CH47", 5: "Cargo Ship", 6: "Locked Crate", 8: "Patrol Helicopter"}
        lines = []
        for marker in snapshot.markers:
            marker_type = int(marker.get("type", 0) or 0)
            if marker_type in event_types:
                lines.append(
                    f"{event_types[marker_type]}  •  x={marker.get('x', 0):.0f}, y={marker.get('y', 0):.0f}"
                )
        self.events_box.configure(state="normal")
        self.events_box.delete("1.0", "end")
        self.events_box.insert("1.0", "\n".join(lines) if lines else "No supported event markers are currently active.")
        self.events_box.configure(state="disabled")

    def on_context_updated(self) -> None:
        self.refresh()
