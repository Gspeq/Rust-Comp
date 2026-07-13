from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from rust_companion_plus.models import RustCredentials
<<<<<<< Updated upstream
from rust_companion_plus.services.live_sync import IntegrationSettings
from rust_companion_plus.ui.common import MUTED, MetricCard, SectionCard, safe_int
=======
from rust_companion_plus.services.server_finder import RustServerFinder
from rust_companion_plus.ui.common import MetricCard, SectionCard, run_in_worker, safe_int
>>>>>>> Stashed changes


class DashboardTab(ctk.CTkScrollableFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            self,
            text="Server Overview",
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))

<<<<<<< Updated upstream
        self.metrics: dict[str, MetricCard] = {}
        metric_specs = [
            (1, 0, "name", "Server"),
            (1, 1, "players", "Players"),
            (1, 2, "rank", "BattleMetrics Rank"),
            (2, 0, "map", "Map"),
            (2, 1, "wipe", "Wipe"),
            (2, 2, "sync", "Live Sync"),
        ]
        for row, column, key, title in metric_specs:
            card = MetricCard(self, title)
            card.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
            self.metrics[key] = card

        self._build_rustplus_card(row=3)
        self._build_integration_card(row=4)
        self._build_intel_card(row=5)
        self._build_events_card(row=6)
        self.refresh()

    def _build_rustplus_card(self, row: int) -> None:
        card = SectionCard(
            self,
            "Rust+ pairing profile",
            "Rust+ tokens are server-specific. Saving a profile lets automatic detection switch back to the right token when you rejoin that server.",
        )
        card.grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.grid(row=card.content_row, column=0, sticky="ew", padx=14, pady=(0, 14))
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)

        creds = self.context.credentials
        self.host = ctk.CTkEntry(form, placeholder_text="Server IP / host")
=======
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
>>>>>>> Stashed changes
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

<<<<<<< Updated upstream
        ctk.CTkButton(form, text="Save server profile", command=self.save_credentials).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=6
=======
        ctk.CTkButton(form, text="Save pairing profile", command=self.save_credentials).grid(
            row=1, column=0, sticky="ew", padx=4, pady=6
>>>>>>> Stashed changes
        )
        self.connect_button = ctk.CTkButton(
            form, text="Detect server and sync everything", command=self.run_full_sync
        )
        self.connect_button.grid(row=1, column=1, sticky="ew", padx=4, pady=6)
        ctk.CTkButton(form, text="Re-detect server", command=self.redetect).grid(
            row=1, column=2, sticky="ew", padx=4, pady=6
        )
        ctk.CTkButton(form, text="Clear timeline", command=self.clear_timeline).grid(
            row=1, column=3, sticky="ew", padx=4, pady=6
        )

<<<<<<< Updated upstream
    def _build_integration_card(self, row: int) -> None:
        card = SectionCard(
            self,
            "Automatic server, BattleMetrics, RustMaps, and parser sync",
            "BattleMetrics works for public server metadata without a token. A token can unlock permitted player data. "
            "RustMaps requires an API key. Secrets are currently stored in the app's local JSON settings, so only use this on your own Windows account.",
        )
        card.grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.grid(row=card.content_row, column=0, sticky="ew", padx=14, pady=(0, 14))
        form.grid_columnconfigure((0, 1, 2), weight=1)

        settings = self.context.settings
        self.auto_detect_var = ctk.BooleanVar(value=settings.auto_detect_server)
        self.auto_sync_var = ctk.BooleanVar(value=settings.auto_sync_enabled)
        self.include_players_var = ctk.BooleanVar(value=settings.battlemetrics_include_players)
        self.rustmaps_generate_var = ctk.BooleanVar(value=settings.rustmaps_auto_generate)
        self.download_map_var = ctk.BooleanVar(value=settings.rustmaps_download_map)
        self.auto_parse_var = ctk.BooleanVar(value=settings.auto_parse_map)

        ctk.CTkCheckBox(form, text="Auto-detect current Rust server", variable=self.auto_detect_var).grid(
            row=0, column=0, sticky="w", padx=6, pady=5
        )
        ctk.CTkCheckBox(form, text="Refresh automatically", variable=self.auto_sync_var).grid(
            row=0, column=1, sticky="w", padx=6, pady=5
        )
        self.interval = ctk.CTkEntry(form, placeholder_text="Refresh seconds (min 30)")
        self.interval.insert(0, str(settings.sync_interval_seconds))
        self.interval.grid(row=0, column=2, sticky="ew", padx=6, pady=5)

        self.bm_token = ctk.CTkEntry(form, placeholder_text="BattleMetrics bearer token (optional)", show="•")
        if settings.battlemetrics_token:
            self.bm_token.insert(0, settings.battlemetrics_token)
        self.bm_token.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=5)
        ctk.CTkCheckBox(
            form,
            text="Request permitted current-player data",
            variable=self.include_players_var,
        ).grid(row=1, column=2, sticky="w", padx=6, pady=5)

        self.rustmaps_key = ctk.CTkEntry(form, placeholder_text="RustMaps API key", show="•")
        if settings.rustmaps_api_key:
            self.rustmaps_key.insert(0, settings.rustmaps_api_key)
        self.rustmaps_key.grid(row=2, column=0, columnspan=3, sticky="ew", padx=6, pady=5)

        ctk.CTkCheckBox(
            form, text="Generate missing procedural map", variable=self.rustmaps_generate_var
        ).grid(row=3, column=0, sticky="w", padx=6, pady=5)
        ctk.CTkCheckBox(
            form, text="Download .map when allowed", variable=self.download_map_var
        ).grid(row=3, column=1, sticky="w", padx=6, pady=5)
        ctk.CTkCheckBox(
            form, text="Run MapParser automatically", variable=self.auto_parse_var
        ).grid(row=3, column=2, sticky="w", padx=6, pady=5)

        ctk.CTkButton(form, text="Save integration settings", command=self.save_integration_settings).grid(
            row=4, column=0, columnspan=3, sticky="ew", padx=6, pady=(8, 4)
        )
        self.sync_status_label = ctk.CTkLabel(form, text="", text_color=MUTED, anchor="w", justify="left")
        self.sync_status_label.grid(row=5, column=0, columnspan=3, sticky="ew", padx=6, pady=(4, 0))

    def _build_intel_card(self, row: int) -> None:
        intel = SectionCard(
            self,
            "Live server intelligence",
            "Detection source, endpoint, wipe metadata, RustMaps details, and integration warnings.",
        )
        intel.grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        self.intel_box = ctk.CTkTextbox(intel, height=220)
        self.intel_box.grid(row=intel.content_row, column=0, sticky="ew", padx=14, pady=(0, 14))
        self.intel_box.configure(state="disabled")

    def _build_events_card(self, row: int) -> None:
        events = SectionCard(self, "Active map events", "Markers supplied by the paired Rust+ server.")
        events.grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        self.events_box = ctk.CTkTextbox(events, height=170)
        self.events_box.grid(row=events.content_row, column=0, sticky="ew", padx=14, pady=(0, 14))
=======
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
>>>>>>> Stashed changes
        self.events_box.configure(state="disabled")
        self.refresh()

<<<<<<< Updated upstream
    def _credentials_from_form(self) -> RustCredentials:
        return RustCredentials(
=======
    def save_credentials(self, *, show_confirmation: bool = True) -> None:
        credentials = RustCredentials(
>>>>>>> Stashed changes
            host=self.host.get().strip(),
            port=safe_int(self.port.get()),
            steam_id=safe_int(self.steam.get()),
            player_token=safe_int(self.token.get()),
        )

    def save_credentials(self, *, show_message: bool = True) -> None:
        credentials = self._credentials_from_form()
        self.context.credentials = credentials
        self.context.store.set("credentials", credentials.to_dict())
<<<<<<< Updated upstream
        server_id = self.context.battlemetrics_server.server_id if self.context.battlemetrics_server else ""
        self.context.save_credential_profile(credentials, server_id)
        if show_message:
            messagebox.showinfo("Rust Companion+", "Rust+ server profile saved locally.")

    def _settings_from_form(self) -> IntegrationSettings:
        return IntegrationSettings(
            auto_detect_server=bool(self.auto_detect_var.get()),
            auto_sync_enabled=bool(self.auto_sync_var.get()),
            sync_interval_seconds=max(30, min(3600, safe_int(self.interval.get(), 60))),
            battlemetrics_token=self.bm_token.get().strip(),
            battlemetrics_include_players=bool(self.include_players_var.get()),
            rustmaps_api_key=self.rustmaps_key.get().strip(),
            rustmaps_auto_generate=bool(self.rustmaps_generate_var.get()),
            rustmaps_download_map=bool(self.download_map_var.get()),
            auto_parse_map=bool(self.auto_parse_var.get()),
        )

    def save_integration_settings(self, *, show_message: bool = True) -> None:
        settings = self._settings_from_form()
        self.context.settings = settings
        self.context.store.set("integration_settings", settings.to_dict())
        self.interval.delete(0, "end")
        self.interval.insert(0, str(settings.sync_interval_seconds))
        if show_message:
            messagebox.showinfo("Rust Companion+", "Automatic integration settings saved.")

    def run_full_sync(self) -> None:
        self.save_credentials(show_message=False)
        self.save_integration_settings(show_message=False)
        self.connect_button.configure(state="disabled", text="Detecting and syncing…")

        def completed(_result) -> None:
            self.connect_button.configure(state="normal", text="Detect server and sync everything")
            self._populate_form_from_context()
            self.refresh()

        self.context.app.run_live_sync(manual=True, on_complete=completed)

    def _populate_form_from_context(self) -> None:
        creds = self.context.credentials
        fields = [
            (self.host, creds.host),
            (self.port, str(creds.port) if creds.port else ""),
            (self.steam, str(creds.steam_id) if creds.steam_id else ""),
            (self.token, str(creds.player_token) if creds.player_token else ""),
        ]
        for widget, value in fields:
            if widget.get() != value:
                widget.delete(0, "end")
                widget.insert(0, value)

    def refresh(self) -> None:
        context = self.context
        snapshot = context.snapshot
        server = snapshot.server if snapshot else {}
        bm = context.battlemetrics_server
        rust_map = context.rustmaps_map

        self.metrics["name"].set(str(server.get("name") or "Not detected"), str(server.get("ip") or ""))
        self.metrics["players"].set(
            f"{server.get('players', 0)}/{server.get('max_players', 0)}",
            f"Queue: {server.get('queued_players', 0)}",
        )
        rank = int(server.get("rank") or 0)
        self.metrics["rank"].set(f"#{rank}" if rank else "—", str(server.get("country") or ""))
        self.metrics["map"].set(
            str(server.get("map") or "Procedural"),
            f"Seed {server.get('seed', '—')} · Size {server.get('size') or server.get('map_size') or '—'}",
        )
        self.metrics["wipe"].set(
            str(server.get("last_wipe") or "Unknown"),
            f"Next: {server.get('next_wipe') or 'not published'}",
        )
        self.metrics["sync"].set(
            "Rust+" if context.rustplus_connected else ("Metadata" if snapshot else "Offline"),
            context.last_synced_at or "Not synced yet",
        )

        self.sync_status_label.configure(
            text=("Working: " if context.sync_in_progress else "") + context.sync_status
        )
        self.connect_button.configure(
            state="disabled" if context.sync_in_progress else "normal",
            text="Detecting and syncing…" if context.sync_in_progress else "Detect server and sync everything",
        )

        lines: list[str] = []
        if context.detected_server:
            detected = context.detected_server
            lines.extend(
                [
                    f"Detection: {detected.source} ({detected.confidence}% confidence)",
                    f"Detected endpoint: {detected.host}:{detected.port or 'unknown port'}",
                ]
            )
        if bm:
            lines.extend(
                [
                    f"BattleMetrics ID: {bm.server_id} · status {bm.status} · rank #{bm.rank or '—'}",
                    f"Game endpoint: {bm.ip}:{bm.port or '—'} · query port {bm.query_port or '—'} · Rust+ app port {bm.companion_port or 'not published'}",
                    f"Population: {bm.players}/{bm.max_players} · queue {bm.queue}",
                    f"Wipe: {bm.last_wipe or 'unknown'} · next {bm.next_wipe or 'not published'}",
                ]
            )
            if bm.current_players:
                preview = ", ".join(bm.current_players[:20])
                extra = f" (+{len(bm.current_players) - 20})" if len(bm.current_players) > 20 else ""
                lines.append(f"Current players permitted by API: {preview}{extra}")
        if rust_map:
            biomes = ", ".join(f"{key.upper()} {value:g}%" for key, value in rust_map.biome_percentages.items())
            lines.extend(
                [
                    f"RustMaps: {rust_map.map_id or 'map found'} · {rust_map.total_monuments} monuments · {rust_map.land_percentage}% land",
                    f"Terrain: {rust_map.islands} islands · {rust_map.mountains} mountains · {rust_map.rivers} rivers · {rust_map.lakes} lakes · {rust_map.canyons} canyons",
                    f"Biomes: {biomes or 'not reported'}",
                    f"Map download/parser: {'allowed' if rust_map.can_download else 'not allowed by RustMaps for this map/account'}",
                ]
            )
        if context.map_cache_dir:
            lines.append(f"Map cache: {context.map_cache_dir}")
        if context.sync_warnings:
            lines.append("Warnings:")
            lines.extend(f"  • {warning}" for warning in context.sync_warnings)
        if not lines:
            lines.append("Join a Rust server, then run the full live sync.")

        self.intel_box.configure(state="normal")
        self.intel_box.delete("1.0", "end")
        self.intel_box.insert("1.0", "\n".join(lines))
        self.intel_box.configure(state="disabled")

        event_types = {4: "Chinook / CH47", 5: "Cargo Ship", 6: "Locked Crate", 8: "Patrol Helicopter"}
        event_lines = []
        if snapshot:
            for marker in snapshot.markers:
                marker_type = int(marker.get("type", 0) or 0)
                if marker_type in event_types:
                    event_lines.append(
                        f"{event_types[marker_type]}  •  x={marker.get('x', 0):.0f}, y={marker.get('y', 0):.0f}"
                    )
        self.events_box.configure(state="normal")
        self.events_box.delete("1.0", "end")
        self.events_box.insert(
            "1.0",
            "\n".join(event_lines)
            if event_lines
            else "No supported Rust+ event markers are currently active.",
        )
        self.events_box.configure(state="disabled")

    def on_context_updated(self) -> None:
        self._populate_form_from_context()
=======

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

        run_in_worker(
            self,
            lambda: RustServerFinder(self.context.store).detect_once(enrich=True),
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
                    f"[BM] Rust+ app port : {bm.get('rust_app_port') or 'not published'}",
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
>>>>>>> Stashed changes
        self.refresh()
