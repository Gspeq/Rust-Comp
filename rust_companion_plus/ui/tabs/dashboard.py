from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.server_finder import RustServerFinder
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
            (2, "endpoint", "Game Endpoint"),
            (3, "time", "Last Update"),
        ]:
            card = MetricCard(self, title)
            card.grid(
                row=1,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 6, 0),
                pady=(0, 12),
            )
            self.metrics[key] = card

        connection = SectionCard(
            self,
            "Rust+ Pairing",
            "The game endpoint is detected independently. The companion/app port and player token "
            "come from Rust+ pairing and are never guessed from the game port.",
        )
        connection.grid(row=2, column=0, columnspan=4, sticky="ew", pady=8)
        form = ctk.CTkFrame(connection, fg_color="transparent")
        form.grid(row=connection.content_row, column=0, sticky="ew", padx=14, pady=(0, 14))
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)

        creds = context.credentials
        self.host = ctk.CTkEntry(form, placeholder_text="Detected server IP / host")
        self.host.insert(0, creds.host)
        self.host.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self.port = ctk.CTkEntry(form, placeholder_text="Rust+ companion/app port")
        if creds.port:
            self.port.insert(0, str(creds.port))
        self.port.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        self.steam = ctk.CTkEntry(form, placeholder_text="Steam ID")
        if creds.steam_id:
            self.steam.insert(0, str(creds.steam_id))
        self.steam.grid(row=0, column=2, sticky="ew", padx=4, pady=4)
        self.token = ctk.CTkEntry(form, placeholder_text="Rust+ player token", show="•")
        if creds.player_token:
            self.token.insert(0, str(creds.player_token))
        self.token.grid(row=0, column=3, sticky="ew", padx=4, pady=4)

        ctk.CTkButton(form, text="Save pairing profile", command=self.save_credentials).grid(
            row=1, column=0, sticky="ew", padx=4, pady=6
        )
        self.connect_button = ctk.CTkButton(
            form, text="Connect and refresh", command=self.connect
        )
        self.connect_button.grid(row=1, column=1, sticky="ew", padx=4, pady=6)
        ctk.CTkButton(form, text="Re-detect server", command=self.redetect).grid(
            row=1, column=2, sticky="ew", padx=4, pady=6
        )
        ctk.CTkButton(form, text="Clear timeline", command=self.clear_timeline).grid(
            row=1, column=3, sticky="ew", padx=4, pady=6
        )

        intelligence = SectionCard(
            self,
            "Server Intelligence",
            "Terminal-style evidence report. It shows the selected endpoint, log source, rejected sockets, "
            "BattleMetrics validation, RustMaps URL and any missing Rust+ data.",
        )
        intelligence.grid(row=3, column=0, columnspan=4, sticky="ew", pady=8)
        self.intelligence_box = ctk.CTkTextbox(
            intelligence,
            height=300,
            fg_color="#050806",
            text_color="#8df58d",
            border_width=1,
            border_color="#244c2a",
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
        )
        self.intelligence_box.grid(
            row=intelligence.content_row, column=0, sticky="ew", padx=14, pady=(0, 14)
        )
        self.intelligence_box.configure(state="disabled")

        live = SectionCard(
            self,
            "Live Server & Team Timeline",
            "Timestamped Rust+ population, team-state and world-event changes. The latest entries stay visible "
            "while the rest of the app is used.",
        )
        live.grid(row=4, column=0, columnspan=4, sticky="ew", pady=8)
        self.events_box = ctk.CTkTextbox(
            live,
            height=230,
            fg_color="#090b0d",
            text_color="#d1d5db",
            border_width=1,
            border_color="#303842",
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
        )
        self.events_box.grid(row=live.content_row, column=0, sticky="ew", padx=14, pady=(0, 14))
        self.events_box.configure(state="disabled")
        self.refresh()

    def save_credentials(self, *, show_confirmation: bool = True) -> None:
        credentials = RustCredentials(
            host=self.host.get().strip(),
            port=safe_int(self.port.get()),
            steam_id=safe_int(self.steam.get()),
            player_token=safe_int(self.token.get()),
        )
        self.context.credentials = credentials
        self.context.store.set("credentials", credentials.to_dict())

        selected = (self.context.detection.get("selected") or {})
        game_port = int(selected.get("port", 0) or 0)
        if credentials.host and game_port:
            profiles = dict(self.context.store.get("credential_profiles", {}) or {})
            profiles[f"{credentials.host}:{game_port}"] = credentials.to_dict()
            self.context.store.set("credential_profiles", profiles)
        self.context.record_event("PAIR", "Rust+ pairing profile saved locally.")
        if show_confirmation:
            messagebox.showinfo("Rust Companion+", "Pairing profile saved locally.")

    def connect(self) -> None:
        self.save_credentials(show_confirmation=False)
        self.connect_button.configure(state="disabled", text="Connecting…")

        def success(snapshot):
            self.connect_button.configure(state="normal", text="Connect and refresh")
            self.context.apply_snapshot(snapshot)
            self.context.notify_data_changed()
            self.refresh()

        def error(exc):
            self.connect_button.configure(state="normal", text="Connect and refresh")
            self.context.record_event("RUST+", f"Manual connection failed: {exc}", "error")
            self.refresh()
            messagebox.showerror("Rust+ connection failed", str(exc))

        run_in_worker(
            self,
            lambda: self.context.rust.fetch_snapshot(self.context.credentials),
            success,
            error,
        )

    def redetect(self) -> None:
        self.context.record_event("DETECT", "Manual server re-detection requested.")

        def success(report):
            self.context.apply_detection(report)
            self._sync_entries_from_context()
            self.context.notify_data_changed()
            self.refresh()

        def work():
            finder = RustServerFinder(self.context.store)
            session = finder.get_rust_process_session()
            return finder.detect_once(
                enrich=True,
                require_running_process=True,
                session_started_at=session.started_at_epoch if session.running else None,
                current_session_only=True,
            )

        run_in_worker(
            self,
            work,
            success,
            lambda exc: messagebox.showerror("Server detection failed", str(exc)),
        )

    def clear_timeline(self) -> None:
        self.context.timeline = []
        self.context.store.set("server_timeline", [])
        self.refresh()

    def _sync_entries_from_context(self) -> None:
        creds = self.context.credentials
        for entry, value in (
            (self.host, creds.host),
            (self.port, str(creds.port) if creds.port else ""),
            (self.steam, str(creds.steam_id) if creds.steam_id else ""),
            (self.token, str(creds.player_token) if creds.player_token else ""),
        ):
            if entry.get() != value:
                entry.delete(0, "end")
                entry.insert(0, value)

    def refresh(self) -> None:
        detection = self.context.detection or {}
        selected = detection.get("selected") or {}
        bm = detection.get("battlemetrics") or {}
        snapshot = self.context.snapshot

        server = snapshot.server if snapshot else {}
        server_name = server.get("name") or bm.get("name") or selected.get("endpoint") or "Waiting for Rust"
        self.metrics["name"].set(str(server_name), str(bm.get("status") or "Not enriched"))

        if snapshot:
            players = int(server.get("players", 0) or 0)
            maximum = int(server.get("max_players", 0) or 0)
            queue = int(server.get("queued_players", 0) or 0)
        else:
            players = int(bm.get("players", 0) or 0)
            maximum = int(bm.get("max_players", 0) or 0)
            queue = int(bm.get("queue", 0) or 0)
        self.metrics["players"].set(
            f"{players}/{maximum}" if maximum else "—",
            f"Queue: {queue}",
        )

        endpoint = selected.get("endpoint") or "Not detected"
        confidence = float(selected.get("confidence", 0) or 0)
        self.metrics["endpoint"].set(str(endpoint), f"{confidence:.0%} confidence" if confidence else "")
        self.metrics["time"].set(
            str(detection.get("scanned_at") or "—"),
            "Automatic detection refresh",
        )

        self._set_box(self.intelligence_box, self._intelligence_text(detection), scroll_end=False)
        self._set_box(self.events_box, self._timeline_text(), scroll_end=True)

    def _intelligence_text(self, detection: dict) -> str:
        selected = detection.get("selected") or {}
        bm = detection.get("battlemetrics") or {}
        lines = [
            "RUST COMPANION+ :: SERVER INTELLIGENCE",
            "Developed by Taylor Marshall",
            "=" * 72,
        ]
        if selected:
            lines.extend(
                [
                    f"[SELECTED] endpoint   : {selected.get('endpoint')}",
                    f"[SELECTED] source     : {selected.get('source')}",
                    f"[SELECTED] confidence : {float(selected.get('confidence', 0) or 0):.0%}",
                    f"[SELECTED] observed   : {selected.get('observed_at') or 'unknown'}",
                    f"[LOG]      path       : {detection.get('log_path') or 'not found'}",
                ]
            )
            map_url = (selected.get("metadata") or {}).get("map_url")
            if map_url:
                lines.append(f"[RUSTMAPS] world URL  : {map_url}")
        else:
            lines.append("[WAITING] No active explicit Rust connection has been selected.")

        if bm:
            lines.extend(
                [
                    "-" * 72,
                    f"[BM] id/status/rank : {bm.get('id') or '?'} / {bm.get('status') or '?'} / #{bm.get('rank') or '?'}",
                    f"[BM] endpoint       : {bm.get('ip') or '?'}:{bm.get('port') or '?'} (query {bm.get('query_port') or '?'})",
                    f"[BM] population     : {bm.get('players', 0)}/{bm.get('max_players', 0)} (queue {bm.get('queue', 0)})",
                    f"[BM] wipe           : {bm.get('wipe') or '?'} -> {bm.get('next_wipe') or '?'}",
                    f"[RUST+] app port     : {detection.get('rust_app_port') or 'not published'} "
                    f"({detection.get('rust_app_port_source') or 'no source'})",
                ]
            )

        candidates = detection.get("candidates") or []
        if candidates:
            lines.append("-" * 72)
            lines.append("ACCEPTED CANDIDATES")
            for item in candidates[-12:]:
                lines.append(
                    f"[CANDIDATE] {item.get('endpoint')} from {item.get('source')} "
                    f"({float(item.get('confidence', 0) or 0):.0%})"
                )

        rejected = detection.get("rejected") or []
        if rejected:
            lines.append("-" * 72)
            lines.append("REJECTED ENDPOINTS")
            for item in rejected[-12:]:
                lines.append(
                    f"[REJECT] {item.get('endpoint')} from {item.get('source')}: {item.get('reason')}"
                )

        warnings = detection.get("warnings") or []
        if warnings:
            lines.append("-" * 72)
            for warning in warnings:
                lines.append(f"[WARN] {warning}")

        debug = detection.get("debug") or []
        if debug:
            lines.append("-" * 72)
            lines.append("DETECTION TRACE")
            for entry in debug[-30:]:
                lines.append(f"[TRACE] {entry}")
        return "\n".join(lines)

    def _timeline_text(self) -> str:
        if not self.context.timeline:
            return "No live changes recorded yet. Rust+ updates will appear here with local timestamps."
        lines = []
        for event in self.context.timeline[-80:]:
            time_value = str(event.get("time") or "")
            time_value = time_value.replace("T", " ")
            lines.append(
                f"[{time_value}] [{str(event.get('category') or 'INFO'):7}] {event.get('message') or ''}"
            )
        return "\n".join(lines)

    @staticmethod
    def _set_box(box: ctk.CTkTextbox, text: str, *, scroll_end: bool) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.see("end" if scroll_end else "1.0")
        box.configure(state="disabled")

    def on_context_updated(self) -> None:
        self._sync_entries_from_context()
        self.refresh()
