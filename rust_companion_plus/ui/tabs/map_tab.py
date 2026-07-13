from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw

from rust_companion_plus.config import APP_DATA_DIR
from rust_companion_plus.models import ResourceOverlay
from rust_companion_plus.services.resource_heatmaps import (
    RESOURCE_DEFINITIONS,
    composite_heatmaps,
    find_best_cache_folder,
    find_map_parser,
    grid_reference,
    load_heatmap_bundle,
    parse_local_map,
    rank_hotspots,
)
from rust_companion_plus.ui.common import MUTED, run_in_worker, safe_float, safe_int


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
        self.resource_checks: dict[str, ctk.CTkCheckBox] = {}
        self.resource_count_labels: dict[str, ctk.CTkLabel] = {}

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text="Map & Resource Heatmaps", font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        self.fetch_button = ctk.CTkButton(header, text="Fetch live map", command=self.fetch_map)
        self.fetch_button.grid(row=0, column=1, padx=5)
        ctk.CTkButton(header, text="Auto-detect cache", command=self.auto_detect_cache).grid(
            row=0, column=2, padx=5
        )
        ctk.CTkButton(header, text="Import parsed folder", command=self.choose_source_folder).grid(
            row=0, column=3, padx=5
        )
        ctk.CTkButton(header, text="Parse local .map", command=self.choose_map_file).grid(
            row=0, column=4, padx=5
        )

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
            text="Connect on the Overview tab, then fetch the live map.\n"
            "Resource heatmaps can also be loaded before connecting.",
            anchor="center",
            justify="center",
        )
        self.map_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.map_status = ctk.CTkLabel(
            map_frame,
            text="No heatmap source loaded.",
            anchor="w",
            text_color=MUTED,
        )
        self.map_status.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

        side_tabs = ctk.CTkTabview(body, width=360)
        side_tabs.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        side_tabs.add("Heatmaps")
        side_tabs.add("Manual notes")
        self._build_heatmap_controls(side_tabs.tab("Heatmaps"))
        self._build_manual_controls(side_tabs.tab("Manual notes"))

        saved_source = str(self.context.store.get("heatmap_source_dir", "") or "")
        if saved_source and Path(saved_source).exists():
            self.after(150, lambda: self.load_heatmap_source(Path(saved_source), quiet=True))

    def _build_heatmap_controls(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(
            parent,
            text="Exact layers come from parsed .map data or imported masks.",
            justify="left",
            wraplength=310,
            anchor="w",
            text_color=MUTED,
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 6))

        size_row = ctk.CTkFrame(parent, fg_color="transparent")
        size_row.grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        size_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(size_row, text="World size").grid(row=0, column=0, padx=(0, 6))
        self.world_size_entry = ctk.CTkEntry(size_row, placeholder_text="e.g. 4500")
        stored_size = safe_int(str(self.context.store.get("heatmap_world_size", 0)))
        if stored_size:
            self.world_size_entry.insert(0, str(stored_size))
        self.world_size_entry.grid(row=0, column=1, sticky="ew")
        self.world_size_entry.bind("<FocusOut>", lambda _event: self.reload_current_source())

        selected = set(self.context.store.get("heatmap_selected_resources", ["Stone", "Metal", "Sulfur"]))
        resource_frame = ctk.CTkScrollableFrame(parent, height=260, label_text="Visible layers")
        resource_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=6)
        resource_frame.grid_columnconfigure(0, weight=1)
        for row, resource in enumerate(RESOURCE_DEFINITIONS):
            line = ctk.CTkFrame(resource_frame, fg_color="transparent")
            line.grid(row=row, column=0, sticky="ew", pady=2)
            line.grid_columnconfigure(0, weight=1)
            check = ctk.CTkCheckBox(line, text=resource, command=self.render_map)
            check.grid(row=0, column=0, sticky="w")
            if resource in selected:
                check.select()
            count = ctk.CTkLabel(line, text="—", text_color=MUTED, width=60, anchor="e")
            count.grid(row=0, column=1, sticky="e")
            self.resource_checks[resource] = check
            self.resource_count_labels[resource] = count

        ctk.CTkLabel(parent, text="Layer opacity").grid(row=3, column=0, sticky="w", padx=10)
        self.opacity_slider = ctk.CTkSlider(parent, from_=0.1, to=1.0, number_of_steps=18, command=lambda _v: self.render_map())
        self.opacity_slider.set(0.68)
        self.opacity_slider.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 8))

        ctk.CTkLabel(parent, text="Density smoothing").grid(row=5, column=0, sticky="w", padx=10)
        self.blur_slider = ctk.CTkSlider(parent, from_=0, to=60, number_of_steps=30, command=lambda _v: self.render_map())
        self.blur_slider.set(24)
        self.blur_slider.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 8))

        ctk.CTkLabel(parent, text="Point influence radius").grid(row=7, column=0, sticky="w", padx=10)
        self.radius_slider = ctk.CTkSlider(parent, from_=3, to=50, number_of_steps=47, command=lambda _v: self.render_map())
        self.radius_slider.set(18)
        self.radius_slider.grid(row=8, column=0, sticky="ew", padx=10, pady=(0, 8))

        ctk.CTkButton(parent, text="Find best hotspots", command=self.refresh_hotspots).grid(
            row=9, column=0, sticky="ew", padx=8, pady=6
        )
        self.hotspot_box = ctk.CTkTextbox(parent, height=210)
        self.hotspot_box.grid(row=10, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.hotspot_box.insert("1.0", "Load a heatmap source, select layers, then rank hotspots.")

    def _build_manual_controls(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(8, weight=1)
        self.resource = ctk.CTkOptionMenu(parent, values=list(MANUAL_COLORS))
        self.resource.grid(row=0, column=0, sticky="ew", padx=8, pady=4)
        self.x_entry = ctk.CTkEntry(parent, placeholder_text="X % (0–100)")
        self.x_entry.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        self.y_entry = ctk.CTkEntry(parent, placeholder_text="Y % (0–100)")
        self.y_entry.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        self.intensity = ctk.CTkEntry(parent, placeholder_text="Intensity 1–5")
        self.intensity.insert(0, "2")
        self.intensity.grid(row=3, column=0, sticky="ew", padx=8, pady=4)
        self.note = ctk.CTkEntry(parent, placeholder_text="Note")
        self.note.grid(row=4, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkButton(parent, text="Add manual zone", command=self.add_overlay).grid(
            row=5, column=0, sticky="ew", padx=8, pady=6
        )
        ctk.CTkButton(parent, text="Clear manual zones", command=self.clear_overlays).grid(
            row=6, column=0, sticky="ew", padx=8, pady=6
        )
        self.overlay_list = ctk.CTkTextbox(parent, height=330)
        self.overlay_list.grid(row=8, column=0, sticky="nsew", padx=8, pady=8)
        self.refresh_overlay_list()

    def current_world_size(self) -> int:
        entered = safe_int(self.world_size_entry.get())
        if entered > 0:
            return entered
        snapshot = self.context.snapshot
        if snapshot:
            server = snapshot.server
            return safe_int(str(server.get("size") or server.get("map_size") or 0))
        return 0

    def selected_resources(self) -> list[str]:
        return [resource for resource, check in self.resource_checks.items() if check.get()]

    def fetch_map(self) -> None:
        self.fetch_button.configure(state="disabled", text="Loading…")

        def success(image):
            self.fetch_button.configure(state="normal", text="Fetch live map")
            self.context.map_image = image
            snapshot_size = self.current_world_size()
            if snapshot_size and not self.world_size_entry.get().strip():
                self.world_size_entry.insert(0, str(snapshot_size))
            self.render_map()

        def error(exc):
            self.fetch_button.configure(state="normal", text="Fetch live map")
            messagebox.showerror("Map request failed", str(exc))

        run_in_worker(
            self,
            lambda: self.context.rust.fetch_map(self.context.credentials),
            success,
            error,
        )

    def choose_source_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose parsed Rust map or heatmap folder")
        if selected:
            self.load_heatmap_source(Path(selected))

    def auto_detect_cache(self) -> None:
        folder = find_best_cache_folder(self.current_world_size())
        if folder is None:
            messagebox.showinfo(
                "No parsed cache found",
                "No compatible RustPlusDesk 3DMaps cache was found. Use Parse local .map or import a parsed folder.",
            )
            return
        self.load_heatmap_source(folder)

    def choose_map_file(self) -> None:
        map_path = filedialog.askopenfilename(
            title="Choose Rust server map",
            filetypes=[("Rust map", "*.map"), ("All files", "*.*")],
        )
        if not map_path:
            return
        parser = find_map_parser()
        if parser is None:
            parser_choice = filedialog.askopenfilename(
                title="Choose compatible MapParser.exe",
                filetypes=[("MapParser", "MapParser.exe"), ("Executable", "*.exe")],
            )
            if not parser_choice:
                messagebox.showerror(
                    "Parser required",
                    "A compatible MapParser.exe is required for direct .map extraction. "
                    "You can instead import an already parsed cache folder.",
                )
                return
            parser = Path(parser_choice)

        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(map_path).stem).strip("_") or "rust_map"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = APP_DATA_DIR / "heatmaps" / f"{safe_name}_{stamp}"
        self.map_status.configure(text="Parsing local .map data…")

        def success(folder: Path) -> None:
            self.load_heatmap_source(folder)

        run_in_worker(
            self,
            lambda: parse_local_map(map_path, output, parser),
            success,
            lambda exc: messagebox.showerror("Map parsing failed", str(exc)),
        )

    def load_heatmap_source(self, source: Path, quiet: bool = False) -> None:
        self.map_status.configure(text=f"Loading heatmap source: {source}")
        world_size = self.current_world_size()

        def success(bundle) -> None:
            self.context.heatmap_bundle = bundle
            self.context.store.set("heatmap_source_dir", str(source))
            if bundle.detected_world_size and not self.world_size_entry.get().strip():
                self.world_size_entry.insert(0, str(bundle.detected_world_size))
            self.context.store.set("heatmap_world_size", self.current_world_size() or bundle.detected_world_size)
            self._try_load_base_map(source)
            self.refresh_resource_counts()
            self.render_map()
            self.refresh_hotspots()
            warnings = " · ".join(bundle.warnings[:2])
            details = f"{len(bundle.resources)} resource types · {bundle.files_scanned} source files"
            self.map_status.configure(text=f"Loaded {source} · {details}" + (f" · {warnings}" if warnings else ""))
            if bundle.warnings and not quiet and not bundle.resources:
                messagebox.showwarning("No recognized heatmap layers", "\n".join(bundle.warnings))

        run_in_worker(
            self,
            lambda: load_heatmap_bundle(source, world_size),
            success,
            lambda exc: messagebox.showerror("Heatmap import failed", str(exc)),
        )

    def reload_current_source(self) -> None:
        source = str(self.context.store.get("heatmap_source_dir", "") or "")
        if source and Path(source).exists():
            self.load_heatmap_source(Path(source), quiet=True)
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
            if candidate.is_file():
                try:
                    with Image.open(candidate) as image:
                        self.context.map_image = image.convert("RGBA").copy()
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
        return list(self.context.store.get("resource_overlays", []))

    def add_overlay(self) -> None:
        raw_x = safe_float(self.x_entry.get(), -1)
        raw_y = safe_float(self.y_entry.get(), -1)
        if not 0 <= raw_x <= 100 or not 0 <= raw_y <= 100:
            messagebox.showerror("Invalid coordinates", "Enter X and Y percentages from 0 to 100.")
            return
        overlay = ResourceOverlay(
            self.resource.get(),
            raw_x / 100.0,
            raw_y / 100.0,
            max(1, min(5, safe_int(self.intensity.get(), 2))),
            self.note.get().strip(),
        )
        rows = self.overlays()
        rows.append(overlay.to_dict())
        self.context.store.set("resource_overlays", rows)
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
                f"{row['resource']} · {row['x_fraction']*100:.0f}%, {row['y_fraction']*100:.0f}% "
                f"· intensity {row.get('intensity', 1)}  {row.get('note', '')}"
            )
        self.overlay_list.delete("1.0", "end")
        self.overlay_list.insert("1.0", "\n".join(lines) if lines else "No manual resource notes yet.")

    def render_map(self) -> None:
        selected = self.selected_resources()
        self.context.store.set("heatmap_selected_resources", selected)
        self.context.store.set("heatmap_world_size", self.current_world_size())
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
            x = int(image.width * float(row["x_fraction"]))
            y = int(image.height * (1.0 - float(row["y_fraction"])))
            radius = 18 + int(row.get("intensity", 1)) * 12
            color = MANUAL_COLORS.get(row["resource"], "#ffffff").lstrip("#")
            rgb = tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(*rgb, 50),
                outline=(*rgb, 240),
                width=4,
            )

        max_width, max_height = 1030, 720
        scale = min(max_width / image.width, max_height / image.height, 1.0)
        display_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        self.ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=display_size)
        self.map_label.configure(image=self.ctk_image, text="")

    def refresh_hotspots(self) -> None:
        hotspots = rank_hotspots(self.context.heatmap_bundle, self.selected_resources())
        world_size = self.current_world_size()
        lines = []
        for index, hotspot in enumerate(hotspots, start=1):
            grid = grid_reference(hotspot.x_fraction, hotspot.y_fraction, world_size)
            if world_size:
                world_x = hotspot.x_fraction * world_size - world_size / 2
                world_y = hotspot.y_fraction * world_size - world_size / 2
                coordinates = f"world ({world_x:.0f}, {world_y:.0f})"
            else:
                coordinates = f"{hotspot.x_fraction*100:.1f}%, {hotspot.y_fraction*100:.1f}%"
            lines.append(
                f"{index}. {grid} · {coordinates} · intensity {hotspot.intensity}/255"
            )
        self.hotspot_box.delete("1.0", "end")
        self.hotspot_box.insert(
            "1.0",
            "\n".join(lines)
            if lines
            else "No hotspot density is available for the selected layers.",
        )

    def on_context_updated(self) -> None:
        snapshot_size = self.current_world_size()
        if snapshot_size and not self.world_size_entry.get().strip():
            self.world_size_entry.insert(0, str(snapshot_size))
        self.render_map()
