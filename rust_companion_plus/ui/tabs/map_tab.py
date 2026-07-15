from __future__ import annotations

from pathlib import Path
from tkinter import messagebox
from typing import Any

import customtkinter as ctk
from PIL import Image

from rust_companion_plus.services.resource_heatmaps import (
    RESOURCE_DEFINITIONS,
    composite_heatmaps,
    grid_reference,
    load_heatmap_bundle,
    rank_hotspots,
)
from rust_companion_plus.services.server_profiles import (
    discover_saved_parsed_map,
    parse_current_server_map,
)
from rust_companion_plus.ui.common import (
    ACCENT,
    MUTED,
    run_in_worker,
)


NO_HEATMAP = "No heatmap"


class MapTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(
            master,
            fg_color="transparent",
        )
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.ctk_image = None
        self.current_source_path = ""
        self.active_layer = ctk.StringVar(
            value=NO_HEATMAP
        )

        header = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        header.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkFrame(
            header,
            fg_color="transparent",
        )
        title.grid(
            row=0,
            column=0,
            sticky="w",
        )
        ctk.CTkLabel(
            title,
            text="Map Intelligence",
            font=ctk.CTkFont(
                size=28,
                weight="bold",
            ),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ctk.CTkLabel(
            title,
            text=(
                "Online loading fetches and analyzes the current Rust+ "
                "map before it appears. Offline mode opens the last "
                "saved analyzed map."
            ),
            text_color=MUTED,
            anchor="w",
            justify="left",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(3, 0),
        )

        self.online_button = ctk.CTkButton(
            header,
            text="Load & analyze current map",
            command=self.load_current_map,
            width=210,
            height=38,
            corner_radius=8,
        )
        self.online_button.grid(
            row=0,
            column=1,
            rowspan=2,
            padx=(8, 6),
        )

        self.saved_button = ctk.CTkButton(
            header,
            text="View saved analyzed map",
            command=self.view_saved_parsed_map,
            width=205,
            height=38,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
        )
        self.saved_button.grid(
            row=0,
            column=2,
            rowspan=2,
            padx=(6, 0),
        )

        body = ctk.CTkFrame(
            self,
            corner_radius=12,
        )
        body.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        body.grid_columnconfigure(0, weight=5)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        map_frame = ctk.CTkFrame(
            body,
            fg_color="#0f172a",
            corner_radius=10,
        )
        map_frame.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=12,
            pady=12,
        )
        map_frame.grid_rowconfigure(0, weight=1)
        map_frame.grid_columnconfigure(0, weight=1)

        self.map_label = ctk.CTkLabel(
            map_frame,
            text=(
                "ONLINE\nLoad & analyze the current map.\n\n"
                "OFFLINE\nOpen the saved analyzed map for this server."
            ),
            anchor="center",
            justify="center",
            text_color=("#94a3b8", "#94a3b8"),
            font=ctk.CTkFont(size=16),
        )
        self.map_label.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=10,
            pady=10,
        )

        self.map_status = ctk.CTkLabel(
            map_frame,
            text=(
                "No heatmap is selected by default."
            ),
            anchor="w",
            text_color=MUTED,
        )
        self.map_status.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
            pady=(0, 12),
        )

        side = ctk.CTkFrame(
            body,
            corner_radius=10,
        )
        side.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(0, 12),
            pady=12,
        )
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(
            side,
            text="Heatmap layer",
            font=ctk.CTkFont(
                size=18,
                weight="bold",
            ),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=14,
            pady=(14, 4),
        )
        ctk.CTkLabel(
            side,
            text=(
                "The base map stays clean until you choose a layer."
            ),
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=310,
        ).grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
            pady=(0, 10),
        )

        self.layer_menu = ctk.CTkOptionMenu(
            side,
            values=(
                [NO_HEATMAP]
                + self._ordered_layers()
            ),
            variable=self.active_layer,
            command=self._layer_changed,
            height=36,
        )
        self.layer_menu.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=14,
            pady=(0, 8),
        )

        self.layer_kind = ctk.CTkLabel(
            side,
            text="Base map only",
            text_color=("#0369a1", "#7dd3fc"),
            anchor="w",
            font=ctk.CTkFont(
                size=11,
                weight="bold",
            ),
        )
        self.layer_kind.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=14,
        )

        self.layer_accuracy = ctk.CTkLabel(
            side,
            text=(
                "Choose a layer after the map analysis completes."
            ),
            text_color=MUTED,
            justify="left",
            anchor="w",
            wraplength=310,
        )
        self.layer_accuracy.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=14,
            pady=(3, 10),
        )

        controls = ctk.CTkFrame(
            side,
            fg_color="transparent",
        )
        controls.grid(
            row=5,
            column=0,
            sticky="ew",
            padx=14,
            pady=2,
        )
        controls.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            controls,
            text="Opacity",
            text_color=MUTED,
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
        )
        self.opacity_slider = ctk.CTkSlider(
            controls,
            from_=0.15,
            to=0.95,
            number_of_steps=16,
            command=lambda _value: self.render_map(),
        )
        self.opacity_slider.set(0.66)
        self.opacity_slider.grid(
            row=0,
            column=1,
            sticky="ew",
        )

        ctk.CTkLabel(
            controls,
            text="Smoothing",
            text_color=MUTED,
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(10, 0),
        )
        self.blur_slider = ctk.CTkSlider(
            controls,
            from_=0,
            to=50,
            number_of_steps=25,
            command=lambda _value: self.render_map(),
        )
        self.blur_slider.set(20)
        self.blur_slider.grid(
            row=1,
            column=1,
            sticky="ew",
            pady=(10, 0),
        )

        actions = ctk.CTkFrame(
            side,
            fg_color="transparent",
        )
        actions.grid(
            row=6,
            column=0,
            sticky="ew",
            padx=14,
            pady=(12, 6),
        )
        actions.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            actions,
            text="Rank selected hot zones",
            command=self.refresh_hotspots,
            height=34,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        ctk.CTkButton(
            actions,
            text="Clear layer",
            command=self.clear_layer,
            height=34,
            fg_color="transparent",
            border_width=1,
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(4, 0),
        )

        ctk.CTkLabel(
            side,
            text="Top zones",
            font=ctk.CTkFont(
                size=14,
                weight="bold",
            ),
            anchor="w",
        ).grid(
            row=7,
            column=0,
            sticky="ew",
            padx=14,
            pady=(8, 3),
        )

        self.hotspot_box = ctk.CTkTextbox(
            side,
            height=260,
            corner_radius=8,
        )
        self.hotspot_box.grid(
            row=10,
            column=0,
            sticky="nsew",
            padx=14,
            pady=(0, 14),
        )
        self._set_hotspot_text(
            "Load a map, then choose one layer."
        )

    @staticmethod
    def _ordered_layers() -> list[str]:
        order = {
            "likelihood": 0,
            "habitat": 1,
            "static": 2,
        }
        return sorted(
            RESOURCE_DEFINITIONS,
            key=lambda name: (
                order.get(
                    str(
                        RESOURCE_DEFINITIONS[name].get(
                            "kind",
                            "static",
                        )
                    ),
                    9,
                ),
                name.casefold(),
            ),
        )

    def _profile_assets(self) -> dict[str, Any]:
        record = self.context.profile_record
        if not isinstance(record, dict):
            return {}
        assets = record.get("assets")
        return (
            dict(assets)
            if isinstance(assets, dict)
            else {}
        )

    def _set_profile_asset(
        self,
        name: str,
        value: Any,
    ) -> None:
        record = dict(
            self.context.profile_record
            if isinstance(
                self.context.profile_record,
                dict,
            )
            else {}
        )
        assets = dict(
            record.get("assets")
            if isinstance(
                record.get("assets"),
                dict,
            )
            else {}
        )
        if value not in (None, ""):
            assets[name] = value
        record["assets"] = assets
        self.context.profile_record = record

    def current_world_size(self) -> int:
        snapshot = self.context.snapshot
        if snapshot is not None:
            server = snapshot.server
            try:
                size = int(
                    server.get("size")
                    or server.get("map_size")
                    or 0
                )
            except (TypeError, ValueError):
                size = 0
            if size > 0:
                return size

        try:
            return max(
                0,
                int(
                    self._profile_assets().get(
                        "world_size"
                    )
                    or 0
                ),
            )
        except (TypeError, ValueError):
            return 0

    def selected_resources(self) -> list[str]:
        layer = self.active_layer.get()
        if layer in RESOURCE_DEFINITIONS:
            return [layer]
        return []

    def _set_busy(
        self,
        busy: bool,
        message: str = "",
    ) -> None:
        state = "disabled" if busy else "normal"
        self.online_button.configure(state=state)
        self.saved_button.configure(state=state)
        if message:
            self.map_status.configure(text=message)

    def load_current_map(self) -> None:
        if not self.context.credentials.is_complete():
            messagebox.showerror(
                "Rust+ profile incomplete",
                (
                    "The current server needs a complete Rust+ "
                    "profile before its live map can be loaded."
                ),
            )
            return

        key = str(
            self.context.active_profile_key or ""
        ).strip()
        if not key:
            messagebox.showerror(
                "No active server profile",
                (
                    "The current server endpoint could not be "
                    "identified."
                ),
            )
            return

        self._set_busy(
            True,
            (
                "Fetching the current Rust+ map and running the "
                "built-in analysis before display…"
            ),
        )
        world_size = self.current_world_size()

        def work():
            image = self.context.rust.fetch_map(
                self.context.credentials
            )
            markers = (
                self.context.snapshot.markers
                if self.context.snapshot is not None
                else []
            )
            result = parse_current_server_map(
                key=key,
                detection=self.context.detection,
                profile_record=self.context.profile_record,
                world_size=world_size,
                map_image=image,
                markers=markers,
                force_refresh=True,
            )
            bundle = load_heatmap_bundle(
                result.source_dir,
                world_size,
            )
            return image, result, bundle

        def success(payload) -> None:
            image, result, bundle = payload
            self.context.map_image = image
            self.context.heatmap_bundle = bundle
            self.current_source_path = str(
                result.source_dir
            )
            self._set_profile_asset(
                "parsed_map_dir",
                str(result.source_dir),
            )
            self._set_profile_asset(
                "world_size",
                (
                    world_size
                    or bundle.detected_world_size
                ),
            )
            if result.map_url:
                self._set_profile_asset(
                    "map_url",
                    result.map_url,
                )

            if result.raw_map_path is not None:
                self._set_profile_asset(
                    "raw_map_path",
                    str(result.raw_map_path),
                )

            vault = self.context.profile_vault
            if vault is not None:
                try:
                    saved = vault.save_map_image(
                        key,
                        image,
                    )
                except Exception:
                    saved = ""
                if saved:
                    self._set_profile_asset(
                        "map_image_path",
                        saved,
                    )

            self.context.store.set(
                "heatmap_source_dir",
                str(result.source_dir),
            )
            self.clear_layer()
            self.render_map()
            if result.exact_parser_status == "ready":
                status_text = (
                    "Current map loaded and parsed with "
                    f"{result.monument_count} named monuments. "
                    "Choose a heatmap layer on the right."
                )
            else:
                status_text = (
                    "Current map loaded with fallback analysis. "
                    "Named monument data is unavailable"
                )
                if result.exact_error:
                    status_text += (
                        ": "
                        + str(result.exact_error)[:150]
                    )
            self._set_busy(
                False,
                status_text,
            )
            self.context.notify_data_changed()

        def error(exc: Exception) -> None:
            self._set_busy(
                False,
                "Current map loading or analysis failed.",
            )
            messagebox.showerror(
                "Current map failed",
                str(exc),
            )

        run_in_worker(
            self,
            work,
            success,
            error,
        )

    def view_saved_parsed_map(self) -> None:
        key = str(
            self.context.active_profile_key or ""
        ).strip()
        if not key:
            messagebox.showerror(
                "No server profile",
                (
                    "The saved server profile could not be "
                    "identified."
                ),
            )
            return

        self._set_busy(
            True,
            "Opening the saved analyzed map…",
        )
        world_size = self.current_world_size()

        def work():
            source = discover_saved_parsed_map(
                key,
                self.context.profile_record,
                world_size,
            )
            if source is None:
                return None

            bundle = load_heatmap_bundle(
                source,
                world_size,
            )
            base_path = (
                Path(source)
                / "current_map_texture.png"
            )
            image = None
            if base_path.is_file():
                with Image.open(base_path) as loaded:
                    image = loaded.convert(
                        "RGBA"
                    ).copy()
            elif self.context.map_image is not None:
                image = self.context.map_image.copy()
            return source, bundle, image

        def success(payload) -> None:
            if payload is None:
                self._set_busy(
                    False,
                    "No saved analyzed map is available.",
                )
                messagebox.showinfo(
                    "No saved analyzed map",
                    (
                        "Load and analyze the current map while "
                        "online, then save this server profile."
                    ),
                )
                return

            source, bundle, image = payload
            if image is None:
                self._set_busy(
                    False,
                    "The saved analysis has no base map image.",
                )
                messagebox.showerror(
                    "Saved map incomplete",
                    (
                        "The saved analysis exists, but its base "
                        "map image is missing."
                    ),
                )
                return

            self.current_source_path = str(source)
            self.context.heatmap_bundle = bundle
            self.context.map_image = image
            self._set_profile_asset(
                "parsed_map_dir",
                str(source),
            )
            self.clear_layer()
            self.render_map()
            self._set_busy(
                False,
                (
                    "Saved analyzed map opened. "
                    "Choose a heatmap layer on the right."
                ),
            )
            self.context.notify_data_changed()

        def error(exc: Exception) -> None:
            self._set_busy(
                False,
                "Saved map loading failed.",
            )
            messagebox.showerror(
                "Saved map failed",
                str(exc),
            )

        run_in_worker(
            self,
            work,
            success,
            error,
        )

    def clear_layer(self) -> None:
        self.active_layer.set(NO_HEATMAP)
        self.layer_kind.configure(
            text="Base map only"
        )
        self.layer_accuracy.configure(
            text=(
                "No heatmap overlay is active."
            )
        )
        self._set_hotspot_text(
            "Choose one layer to rank its top zones."
        )
        self.render_map()

    def _layer_changed(
        self,
        layer: str,
    ) -> None:
        if layer not in RESOURCE_DEFINITIONS:
            self.clear_layer()
            return

        kind = str(
            RESOURCE_DEFINITIONS[layer].get(
                "kind",
                "static",
            )
        )
        labels = {
            "likelihood": "Predictive likelihood",
            "habitat": "Predictive habitat",
            "static": "Map-derived layer",
        }
        self.layer_kind.configure(
            text=labels.get(kind, "Map layer")
        )

        if kind == "likelihood":
            detail = (
                "Estimated from visible biome, terrain, and road "
                "evidence. This is not an exact live node map."
            )
        elif kind == "habitat":
            detail = (
                "Estimated habitat suitability. Animals are dynamic "
                "and exact live positions are not exposed here."
            )
        elif layer == "Monument Proximity":
            detail = (
                "Approximate visible monument-marker centers after "
                "known live map markers are excluded."
            )
        else:
            detail = (
                "Derived directly from visible pixels in the "
                "analyzed Rust+ map."
            )
        self.layer_accuracy.configure(text=detail)
        self.render_map()
        self.refresh_hotspots()

    def render_map(self) -> None:
        image = self.context.map_image
        if image is None:
            return

        layer = self.active_layer.get()
        selected = (
            [layer]
            if layer in RESOURCE_DEFINITIONS
            else []
        )
        rendered = composite_heatmaps(
            image,
            self.context.heatmap_bundle,
            selected,
            opacity=float(
                self.opacity_slider.get()
            ),
            point_radius=18,
            blur_radius=int(
                self.blur_slider.get()
            ),
        )

        available_width = max(
            760,
            self.map_label.winfo_width() - 20,
        )
        available_height = max(
            620,
            self.map_label.winfo_height() - 20,
        )
        rendered.thumbnail(
            (
                available_width,
                available_height,
            ),
            Image.Resampling.LANCZOS,
        )
        self.ctk_image = ctk.CTkImage(
            light_image=rendered,
            dark_image=rendered,
            size=rendered.size,
        )
        self.map_label.configure(
            image=self.ctk_image,
            text="",
        )

    def refresh_hotspots(self) -> None:
        layer = self.active_layer.get()
        if layer not in RESOURCE_DEFINITIONS:
            self._set_hotspot_text(
                "Choose one heatmap layer first."
            )
            return

        bundle = self.context.heatmap_bundle
        if bundle is None:
            self._set_hotspot_text(
                "Load and analyze a map first."
            )
            return

        hotspots = rank_hotspots(
            bundle,
            [layer],
            limit=8,
        )
        if not hotspots:
            self._set_hotspot_text(
                (
                    f"No usable {layer} intensity was found "
                    "in the current analysis."
                )
            )
            return

        world_size = self.current_world_size()
        lines = [
            f"TOP {layer.upper()} ZONES",
            "",
        ]
        for index, hotspot in enumerate(
            hotspots,
            start=1,
        ):
            grid = grid_reference(
                hotspot.x_fraction,
                hotspot.y_fraction,
                world_size,
            )
            lines.append(
                (
                    f"{index}. Grid {grid}  ·  "
                    f"intensity {hotspot.intensity}/255"
                )
            )
        lines.extend(
            [
                "",
                (
                    "Hot zones rank the selected layer only. "
                    "Predictive layers are estimates, not live "
                    "entity coordinates."
                ),
            ]
        )
        self._set_hotspot_text(
            "\n".join(lines)
        )

    def _set_hotspot_text(
        self,
        text: str,
    ) -> None:
        self.hotspot_box.delete("1.0", "end")
        self.hotspot_box.insert("1.0", text)

    def on_context_updated(self) -> None:
        # Data refreshes never auto-enable a heatmap.
        if (
            self.context.map_image is not None
            and self.map_label.cget("text")
            == ""
        ):
            self.render_map()
