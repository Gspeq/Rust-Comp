
from __future__ import annotations

from pathlib import Path
from tkinter import messagebox
from typing import Any

import customtkinter as ctk
from PIL import Image, ImageDraw

from rust_companion_plus.models import ResourceOverlay
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
    MUTED,
    run_in_worker,
    safe_float,
    safe_int,
)


MANUAL_COLORS = {
    "Stone": "#a3a3a3",
    "Metal": "#60a5fa",
    "Sulfur": "#facc15",
    "Wood": "#22c55e",
    "Cloth": "#f9a8d4",
}


class MapTab(ctk.CTkFrame):
    def __init__(self, master, context):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.ctk_image = None
        self.current_source_path = ""
        self.resource_checks: dict[str, ctk.CTkCheckBox] = {}
        self.resource_count_labels: dict[str, ctk.CTkLabel] = {}

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkFrame(header, fg_color="transparent")
        title.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title,
            text="Map Intelligence & Heatmaps",
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title,
            text=(
                "Current and saved map assets are matched to this "
                "server profile automatically."
            ),
            text_color=MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.fetch_button = ctk.CTkButton(
            header,
            text="Load current map",
            command=self.load_current_map,
            width=150,
        )
        self.fetch_button.grid(row=0, column=1, rowspan=2, padx=5)

        self.saved_button = ctk.CTkButton(
            header,
            text="View saved parsed map",
            command=self.view_saved_parsed_map,
            width=185,
        )
        self.saved_button.grid(row=0, column=2, rowspan=2, padx=5)

        self.parse_button = ctk.CTkButton(
            header,
            text="Analyze current map",
            command=self.parse_current_map,
            width=160,
        )
        self.parse_button.grid(row=0, column=3, rowspan=2, padx=(5, 0))

        body = ctk.CTkFrame(self)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=5)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        map_frame = ctk.CTkFrame(body, fg_color="#111827")
        map_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        map_frame.grid_rowconfigure(0, weight=1)
        map_frame.grid_columnconfigure(0, weight=1)

        self.map_label = ctk.CTkLabel(
            map_frame,
            text=(
                "Load the current Rust+ map, open this profile's saved "
                "parsed map, or parse the detected current map."
            ),
            anchor="center",
            justify="center",
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
            text="No profile map asset loaded.",
            anchor="w",
            text_color=MUTED,
        )
        self.map_status.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=12,
            pady=(0, 10),
        )

        side_tabs = ctk.CTkTabview(body, width=360)
        side_tabs.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(0, 10),
            pady=10,
        )
        side_tabs.add("Heatmaps")
        side_tabs.add("Manual notes")
        self._build_heatmap_controls(side_tabs.tab("Heatmaps"))
        self._build_manual_controls(side_tabs.tab("Manual notes"))

        assets = self._profile_assets()
        source = str(assets.get("parsed_map_dir") or "").strip()
        if source and Path(source).exists():
            self.after(
                150,
                lambda: self.load_heatmap_source(
                    Path(source),
                    quiet=True,
                ),
            )
        if self.context.map_image is not None:
            self.after(175, self.render_map)

    def _build_heatmap_controls(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(
            parent,
            text=(
                "Exact layers are loaded from this server profile's "
                "automatically detected parsed map."
            ),
            justify="left",
            wraplength=310,
            anchor="w",
            text_color=MUTED,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=8,
            pady=(8, 6),
        )

        size_row = ctk.CTkFrame(parent, fg_color="transparent")
        size_row.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=6,
            pady=4,
        )
        size_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            size_row,
            text="World size",
            text_color=MUTED,
        ).grid(row=0, column=0, padx=(0, 8))
        self.world_size_label = ctk.CTkLabel(
            size_row,
            text="Automatic",
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        )
        self.world_size_label.grid(
            row=0,
            column=1,
            sticky="ew",
        )

        selected = set(
            self.context.store.get(
                "heatmap_selected_resources",
                ["Stone", "Metal", "Sulfur"],
            )
        )
        profile_selected = self._profile_assets().get(
            "selected_resources"
        )
        if isinstance(profile_selected, list):
            selected = set(str(item) for item in profile_selected)

        resource_frame = ctk.CTkScrollableFrame(
            parent,
            height=260,
            label_text="Visible layers",
        )
        resource_frame.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=6,
            pady=6,
        )
        resource_frame.grid_columnconfigure(0, weight=1)

        for row, resource in enumerate(RESOURCE_DEFINITIONS):
            line = ctk.CTkFrame(
                resource_frame,
                fg_color="transparent",
            )
            line.grid(row=row, column=0, sticky="ew", pady=2)
            line.grid_columnconfigure(0, weight=1)
            check = ctk.CTkCheckBox(
                line,
                text=resource,
                command=self.render_map,
            )
            check.grid(row=0, column=0, sticky="w")
            if resource in selected:
                check.select()
            count = ctk.CTkLabel(
                line,
                text="—",
                text_color=MUTED,
                width=60,
                anchor="e",
            )
            count.grid(row=0, column=1, sticky="e")
            self.resource_checks[resource] = check
            self.resource_count_labels[resource] = count

        ctk.CTkLabel(
            parent,
            text="Layer opacity",
        ).grid(row=3, column=0, sticky="w", padx=10)
        self.opacity_slider = ctk.CTkSlider(
            parent,
            from_=0.1,
            to=1.0,
            number_of_steps=18,
            command=lambda _value: self.render_map(),
        )
        self.opacity_slider.set(0.68)
        self.opacity_slider.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=10,
            pady=(0, 8),
        )

        ctk.CTkLabel(
            parent,
            text="Density smoothing",
        ).grid(row=5, column=0, sticky="w", padx=10)
        self.blur_slider = ctk.CTkSlider(
            parent,
            from_=0,
            to=60,
            number_of_steps=30,
            command=lambda _value: self.render_map(),
        )
        self.blur_slider.set(24)
        self.blur_slider.grid(
            row=6,
            column=0,
            sticky="ew",
            padx=10,
            pady=(0, 8),
        )

        ctk.CTkLabel(
            parent,
            text="Point influence radius",
        ).grid(row=7, column=0, sticky="w", padx=10)
        self.radius_slider = ctk.CTkSlider(
            parent,
            from_=3,
            to=50,
            number_of_steps=47,
            command=lambda _value: self.render_map(),
        )
        self.radius_slider.set(18)
        self.radius_slider.grid(
            row=8,
            column=0,
            sticky="ew",
            padx=10,
            pady=(0, 8),
        )

        ctk.CTkButton(
            parent,
            text="Find best hotspots",
            command=self.refresh_hotspots,
        ).grid(
            row=9,
            column=0,
            sticky="ew",
            padx=8,
            pady=6,
        )
        self.hotspot_box = ctk.CTkTextbox(
            parent,
            height=210,
        )
        self.hotspot_box.grid(
            row=10,
            column=0,
            sticky="nsew",
            padx=8,
            pady=(4, 8),
        )
        self.hotspot_box.insert(
            "1.0",
            "Load or analyze this server's map, select layers, then rank terrain/habitat hotspots.",
        )

    def _build_manual_controls(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(8, weight=1)

        self.resource = ctk.CTkOptionMenu(
            parent,
            values=list(MANUAL_COLORS),
        )
        self.resource.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=8,
            pady=4,
        )
        self.x_entry = ctk.CTkEntry(
            parent,
            placeholder_text="X % (0–100)",
        )
        self.x_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=8,
            pady=4,
        )
        self.y_entry = ctk.CTkEntry(
            parent,
            placeholder_text="Y % (0–100)",
        )
        self.y_entry.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=8,
            pady=4,
        )
        self.intensity = ctk.CTkEntry(
            parent,
            placeholder_text="Intensity 1–5",
        )
        self.intensity.insert(0, "2")
        self.intensity.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=8,
            pady=4,
        )
        self.note = ctk.CTkEntry(
            parent,
            placeholder_text="Note",
        )
        self.note.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=8,
            pady=4,
        )
        ctk.CTkButton(
            parent,
            text="Add manual zone",
            command=self.add_overlay,
        ).grid(
            row=5,
            column=0,
            sticky="ew",
            padx=8,
            pady=6,
        )
        ctk.CTkButton(
            parent,
            text="Clear manual zones",
            command=self.clear_overlays,
        ).grid(
            row=6,
            column=0,
            sticky="ew",
            padx=8,
            pady=6,
        )
        self.overlay_list = ctk.CTkTextbox(
            parent,
            height=330,
        )
        self.overlay_list.grid(
            row=8,
            column=0,
            sticky="nsew",
            padx=8,
            pady=8,
        )
        self.refresh_overlay_list()

    def _profile_assets(self) -> dict[str, Any]:
        record = self.context.profile_record
        if not isinstance(record, dict):
            return {}
        assets = record.get("assets")
        return dict(assets) if isinstance(assets, dict) else {}

    def _set_profile_asset(
        self,
        name: str,
        value: Any,
    ) -> None:
        record = dict(
            self.context.profile_record
            if isinstance(self.context.profile_record, dict)
            else {}
        )
        assets = dict(
            record.get("assets")
            if isinstance(record.get("assets"), dict)
            else {}
        )
        if value not in (None, ""):
            assets[name] = value
        record["assets"] = assets
        self.context.profile_record = record

    def current_world_size(self) -> int:
        snapshot = self.context.snapshot
        if snapshot:
            server = snapshot.server
            size = safe_int(
                str(
                    server.get("size")
                    or server.get("map_size")
                    or 0
                )
            )
            if size > 0:
                self.world_size_label.configure(text=str(size))
                return size

        size = safe_int(
            str(self._profile_assets().get("world_size") or 0)
        )
        if size <= 0:
            size = safe_int(
                str(
                    self.context.store.get(
                        "heatmap_world_size",
                        0,
                    )
                )
            )
        self.world_size_label.configure(
            text=str(size) if size > 0 else "Unknown"
        )
        return max(0, size)

    def selected_resources(self) -> list[str]:
        return [
            resource
            for resource, check in self.resource_checks.items()
            if check.get()
        ]

    def load_current_map(self) -> None:
        if not self.context.credentials.is_complete():
            messagebox.showerror(
                "Rust+ profile incomplete",
                "This server profile does not have complete Rust+ credentials.",
            )
            return

        self.fetch_button.configure(
            state="disabled",
            text="Loading current map…",
        )

        def success(image) -> None:
            self.fetch_button.configure(
                state="normal",
                text="Load current map",
            )
            self.context.map_image = image
            key = str(self.context.active_profile_key or "").strip()
            vault = self.context.profile_vault
            if key and vault is not None:
                try:
                    saved = vault.save_map_image(key, image)
                except Exception as exc:
                    self.map_status.configure(
                        text=f"Current map loaded; local map cache failed: {exc}"
                    )
                else:
                    if saved:
                        self._set_profile_asset(
                            "map_image_path",
                            saved,
                        )
            self.map_status.configure(
                text=(
                    "Current Rust+ map loaded for this profile. "
                    "Save the profile on close to keep the complete archive."
                )
            )
            self.render_map()

        def error(exc: Exception) -> None:
            self.fetch_button.configure(
                state="normal",
                text="Load current map",
            )
            messagebox.showerror(
                "Map request failed",
                str(exc),
            )

        run_in_worker(
            self,
            lambda: self.context.rust.fetch_map(
                self.context.credentials
            ),
            success,
            error,
        )

    def view_saved_parsed_map(self) -> None:
        key = str(self.context.active_profile_key or "").strip()
        if not key:
            messagebox.showerror(
                "No server profile",
                "The current server profile could not be identified.",
            )
            return

        self.saved_button.configure(
            state="disabled",
            text="Finding saved map…",
        )
        world_size = self.current_world_size()

        def work() -> Path | None:
            return discover_saved_parsed_map(
                key,
                self.context.profile_record,
                world_size,
            )

        def success(source: Path | None) -> None:
            self.saved_button.configure(
                state="normal",
                text="View saved parsed map",
            )
            if source is None:
                messagebox.showinfo(
                    "No saved parsed map",
                    "No parsed map is associated with this server profile yet. "
                    "Use Analyze current map; the app will locate the map and parser automatically.",
                )
                return
            self._set_profile_asset(
                "parsed_map_dir",
                str(source),
            )
            self.load_heatmap_source(source)

        def error(exc: Exception) -> None:
            self.saved_button.configure(
                state="normal",
                text="View saved parsed map",
            )
            messagebox.showerror(
                "Saved map lookup failed",
                str(exc),
            )

        run_in_worker(self, work, success, error)

    def parse_current_map(self) -> None:
        key = str(
            self.context.active_profile_key or ""
        ).strip()
        if not key:
            messagebox.showerror(
                "No server profile",
                "The current server profile could not be identified.",
            )
            return

        self.parse_button.configure(
            state="disabled",
            text="Analyzing current map…",
        )
        self.map_status.configure(
            text=(
                "Running the built-in terrain, biome, ore-likelihood, "
                "animal-habitat, road, and coastline analyzer…"
            )
        )
        world_size = self.current_world_size()

        def work():
            image = self.context.map_image
            if image is None:
                if not self.context.credentials.is_complete():
                    raise ValueError(
                        "The current server has no complete Rust+ profile "
                        "and no saved map image."
                    )
                image = self.context.rust.fetch_map(
                    self.context.credentials
                )

            snapshot = self.context.snapshot
            markers = (
                list(snapshot.markers)
                if snapshot is not None
                else []
            )
            result = parse_current_server_map(
                key=key,
                detection=self.context.detection,
                profile_record=self.context.profile_record,
                world_size=world_size,
                map_image=image,
                markers=markers,
            )
            return result, image

        def success(payload) -> None:
            result, image = payload
            self.parse_button.configure(
                state="normal",
                text="Analyze current map",
            )
            self.context.map_image = image
            self._set_profile_asset(
                "parsed_map_dir",
                str(result.source_dir),
            )
            if result.raw_map_path is not None:
                self._set_profile_asset(
                    "raw_map_path",
                    str(result.raw_map_path),
                )
            if result.map_url:
                self._set_profile_asset(
                    "map_url",
                    result.map_url,
                )

            key_value = str(
                self.context.active_profile_key or ""
            ).strip()
            vault = self.context.profile_vault
            if key_value and vault is not None:
                try:
                    saved = vault.save_map_image(
                        key_value,
                        image,
                    )
                except Exception:
                    saved = ""
                if saved:
                    self._set_profile_asset(
                        "map_image_path",
                        saved,
                    )

            self.load_heatmap_source(
                result.source_dir,
                quiet=not result.created,
            )
            if result.created:
                self.map_status.configure(
                    text=(
                        "Built-in map analysis complete. Static terrain "
                        "layers are map-derived; ore and animal layers are "
                        "clearly labeled suitability estimates because live "
                        "spawns are dynamic."
                    )
                )
            else:
                self.map_status.configure(
                    text=(
                        "This server's built-in map analysis was already "
                        "saved and has been loaded."
                    )
                )

        def error(exc: Exception) -> None:
            self.parse_button.configure(
                state="normal",
                text="Analyze current map",
            )
            self.map_status.configure(
                text="Built-in current map analysis failed."
            )
            messagebox.showerror(
                "Current map analysis failed",
                str(exc),
            )

        run_in_worker(
            self,
            work,
            success,
            error,
        )


    def load_heatmap_source(
        self,
        source: Path,
        quiet: bool = False,
    ) -> None:
        source = Path(source)
        self.map_status.configure(
            text=f"Loading saved parsed map: {source}"
        )
        world_size = self.current_world_size()

        def success(bundle) -> None:
            self.context.heatmap_bundle = bundle
            self.current_source_path = str(source)
            self._set_profile_asset(
                "parsed_map_dir",
                str(source),
            )
            if bundle.detected_world_size:
                self._set_profile_asset(
                    "world_size",
                    bundle.detected_world_size,
                )
            self.context.store.set(
                "heatmap_source_dir",
                str(source),
            )
            self.context.store.set(
                "heatmap_world_size",
                (
                    self.current_world_size()
                    or bundle.detected_world_size
                ),
            )
            self._try_load_base_map(source)
            self.refresh_resource_counts()
            self.render_map()
            self.refresh_hotspots()
            warnings = " · ".join(bundle.warnings[:2])
            details = (
                f"{len(bundle.resources)} resource types · "
                f"{bundle.files_scanned} source files"
            )
            self.map_status.configure(
                text=(
                    f"Loaded saved parsed map · {details}"
                    + (f" · {warnings}" if warnings else "")
                )
            )
            if (
                bundle.warnings
                and not quiet
                and not bundle.resources
            ):
                messagebox.showwarning(
                    "No recognized heatmap layers",
                    "\n".join(bundle.warnings),
                )

        run_in_worker(
            self,
            lambda: load_heatmap_bundle(
                source,
                world_size,
            ),
            success,
            lambda exc: messagebox.showerror(
                "Saved parsed map failed",
                str(exc),
            ),
        )

    def reload_current_source(self) -> None:
        source = self.current_source_path
        if source and Path(source).exists():
            self.load_heatmap_source(
                Path(source),
                quiet=True,
            )
        else:
            self.render_map()

    def _try_load_base_map(self, source: Path) -> None:
        if self.context.map_image is not None:
            return
        root = source if source.is_dir() else source.parent
        candidates = [
            root / "map_texture.png",
            root / "current_map_texture.png",
            root / "map.png",
        ]
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                with Image.open(candidate) as image:
                    self.context.map_image = (
                        image.convert("RGBA").copy()
                    )
                return
            except OSError:
                continue

    def refresh_resource_counts(self) -> None:
        bundle = self.context.heatmap_bundle
        for resource, label in self.resource_count_labels.items():
            if bundle is None:
                label.configure(text="—")
                continue
            points = len(bundle.points.get(resource, []))
            masks = len(bundle.raster_layers.get(resource, []))
            if points and masks:
                text = f"{points} + {masks}m"
            elif points:
                text = str(points)
            elif masks:
                text = f"{masks} mask"
            else:
                text = "0"
            label.configure(text=text)

    def overlays(self) -> list[dict]:
        return list(
            self.context.store.get(
                "resource_overlays",
                [],
            )
        )

    def add_overlay(self) -> None:
        raw_x = safe_float(self.x_entry.get(), -1)
        raw_y = safe_float(self.y_entry.get(), -1)
        if not 0 <= raw_x <= 100 or not 0 <= raw_y <= 100:
            messagebox.showerror(
                "Invalid coordinates",
                "Enter X and Y percentages from 0 to 100.",
            )
            return
        overlay = ResourceOverlay(
            self.resource.get(),
            raw_x / 100.0,
            raw_y / 100.0,
            max(
                1,
                min(
                    5,
                    safe_int(self.intensity.get(), 2),
                ),
            ),
            self.note.get().strip(),
        )
        rows = self.overlays()
        rows.append(overlay.to_dict())
        self.context.store.set(
            "resource_overlays",
            rows,
        )
        self.refresh_overlay_list()
        self.render_map()

    def clear_overlays(self) -> None:
        self.context.store.set("resource_overlays", [])
        self.refresh_overlay_list()
        self.render_map()

    def refresh_overlay_list(self) -> None:
        lines = []
        for row in self.overlays():
            lines.append(
                f"{row['resource']} · "
                f"{row['x_fraction'] * 100:.0f}%, "
                f"{row['y_fraction'] * 100:.0f}% · "
                f"intensity {row.get('intensity', 1)}  "
                f"{row.get('note', '')}"
            )
        self.overlay_list.delete("1.0", "end")
        self.overlay_list.insert(
            "1.0",
            "\n".join(lines)
            if lines
            else "No manual resource notes yet.",
        )

    def render_map(self) -> None:
        selected = self.selected_resources()
        self.context.store.set(
            "heatmap_selected_resources",
            selected,
        )
        self._set_profile_asset(
            "selected_resources",
            selected,
        )
        self._set_profile_asset(
            "world_size",
            self.current_world_size(),
        )
        self.context.store.set(
            "heatmap_world_size",
            self.current_world_size(),
        )
        if self.context.map_image is None:
            return

        image = composite_heatmaps(
            self.context.map_image.copy(),
            self.context.heatmap_bundle,
            selected,
            opacity=float(self.opacity_slider.get()),
            point_radius=int(self.radius_slider.get()),
            blur_radius=int(self.blur_slider.get()),
        ).convert("RGBA")

        draw = ImageDraw.Draw(image, "RGBA")
        for row in self.overlays():
            x = int(
                image.width * float(row["x_fraction"])
            )
            y = int(
                image.height
                * (1.0 - float(row["y_fraction"]))
            )
            radius = (
                18
                + int(row.get("intensity", 1)) * 12
            )
            color = MANUAL_COLORS.get(
                row["resource"],
                "#ffffff",
            ).lstrip("#")
            rgb = tuple(
                int(color[index : index + 2], 16)
                for index in (0, 2, 4)
            )
            draw.ellipse(
                (
                    x - radius,
                    y - radius,
                    x + radius,
                    y + radius,
                ),
                fill=(*rgb, 50),
                outline=(*rgb, 240),
                width=4,
            )

        max_width, max_height = 1030, 720
        scale = min(
            max_width / image.width,
            max_height / image.height,
            1.0,
        )
        display_size = (
            max(1, int(image.width * scale)),
            max(1, int(image.height * scale)),
        )
        self.ctk_image = ctk.CTkImage(
            light_image=image,
            dark_image=image,
            size=display_size,
        )
        self.map_label.configure(
            image=self.ctk_image,
            text="",
        )

    def refresh_hotspots(self) -> None:
        hotspots = rank_hotspots(
            self.context.heatmap_bundle,
            self.selected_resources(),
        )
        world_size = self.current_world_size()
        lines = []
        for index, hotspot in enumerate(
            hotspots,
            start=1,
        ):
            grid = grid_reference(
                hotspot.x_fraction,
                hotspot.y_fraction,
                world_size,
            )
            if world_size:
                world_x = (
                    hotspot.x_fraction * world_size
                    - world_size / 2
                )
                world_y = (
                    hotspot.y_fraction * world_size
                    - world_size / 2
                )
                coordinates = (
                    f"world ({world_x:.0f}, {world_y:.0f})"
                )
            else:
                coordinates = (
                    f"{hotspot.x_fraction * 100:.1f}%, "
                    f"{hotspot.y_fraction * 100:.1f}%"
                )
            lines.append(
                f"{index}. {grid} · {coordinates} · "
                f"intensity {hotspot.intensity}/255"
            )
        self.hotspot_box.delete("1.0", "end")
        self.hotspot_box.insert(
            "1.0",
            "\n".join(lines)
            if lines
            else (
                "No hotspot density is available for "
                "the selected layers."
            ),
        )

    def on_context_updated(self) -> None:
        self.current_world_size()
        self.render_map()
