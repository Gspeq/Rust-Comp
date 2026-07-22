from __future__ import annotations

from typing import Any

import customtkinter as ctk
from PIL import Image

from rust_companion_plus.services.resource_heatmaps import (
    RESOURCE_DEFINITIONS,
    composite_heatmaps,
)
from rust_companion_plus.services.starter_spot import recommend_starter_spots
from rust_companion_plus.ui.common import MUTED, run_in_worker
from rust_companion_plus.ui.tabs.map_tab import (
    HEATMAP_BLUR_RADIUS,
    HEATMAP_OPACITY,
    MapTab as BaseMapTab,
)


ZOOM_LEVELS = ("Fit", "1.5x", "2x", "3x", "4x")


def zoom_crop(
    image: Image.Image,
    zoom: float,
    center: tuple[float, float],
) -> Image.Image:
    source = image.convert("RGBA")
    if zoom <= 1.0:
        return source.copy()

    width, height = source.size
    crop_width = max(32, int(round(width / zoom)))
    crop_height = max(32, int(round(height / zoom)))
    cx = min(1.0, max(0.0, float(center[0]))) * width
    cy = min(1.0, max(0.0, float(center[1]))) * height
    left = int(round(cx - crop_width / 2))
    top = int(round(cy - crop_height / 2))
    left = min(max(0, left), max(0, width - crop_width))
    top = min(max(0, top), max(0, height - crop_height))
    right = min(width, left + crop_width)
    bottom = min(height, top + crop_height)
    return source.crop((left, top, right, bottom)).resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )


class MapTab(BaseMapTab):
    """Existing map intelligence plus bounded zoom and starter-base ranking."""

    def __init__(self, master, context):
        self.zoom_level = ctk.StringVar(value="Fit")
        self.zoom_center = (0.5, 0.5)
        self._starter_busy = False
        self._starter_spots = []
        super().__init__(master, context)

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=0, column=0, sticky="e", padx=(0, 435), pady=(0, 12))
        ctk.CTkLabel(
            controls,
            text="Zoom",
            text_color=MUTED,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=0, padx=(0, 6))
        self.zoom_menu = ctk.CTkOptionMenu(
            controls,
            values=list(ZOOM_LEVELS),
            variable=self.zoom_level,
            width=92,
            command=lambda _value: self.render_map(),
        )
        self.zoom_menu.grid(row=0, column=1, padx=(0, 6))
        ctk.CTkButton(
            controls,
            text="Reset view",
            width=92,
            height=32,
            fg_color="transparent",
            border_width=1,
            command=self.reset_zoom,
        ).grid(row=0, column=2, padx=3)
        self.starter_button = ctk.CTkButton(
            controls,
            text="Recommend starter spot",
            width=176,
            height=32,
            command=self.recommend_starter_spot,
        )
        self.starter_button.grid(row=0, column=3, padx=(3, 0))

        self.map_label.bind("<MouseWheel>", self._mouse_wheel_zoom, add="+")
        self.map_label.bind("<Button-1>", self._focus_clicked_point, add="+")

    def _zoom_number(self) -> float:
        raw = self.zoom_level.get().strip().casefold().removesuffix("x")
        if raw == "fit":
            return 1.0
        try:
            return max(1.0, float(raw))
        except ValueError:
            return 1.0

    def reset_zoom(self) -> None:
        self.zoom_level.set("Fit")
        self.zoom_center = (0.5, 0.5)
        self.render_map()

    def _mouse_wheel_zoom(self, event: Any) -> None:
        current = ZOOM_LEVELS.index(self.zoom_level.get()) if self.zoom_level.get() in ZOOM_LEVELS else 0
        direction = 1 if int(getattr(event, "delta", 0) or 0) > 0 else -1
        target = min(len(ZOOM_LEVELS) - 1, max(0, current + direction))
        self.zoom_level.set(ZOOM_LEVELS[target])
        self.render_map()

    def _focus_clicked_point(self, event: Any) -> None:
        width = max(1, int(self.map_label.winfo_width()))
        height = max(1, int(self.map_label.winfo_height()))
        self.zoom_center = (
            min(1.0, max(0.0, float(event.x) / width)),
            min(1.0, max(0.0, float(event.y) / height)),
        )
        if self._zoom_number() <= 1.0:
            self.zoom_level.set("2x")
        self.render_map()

    def render_map(self) -> None:
        image = self._base_map_for_render()
        if image is None:
            return

        layer = self.active_layer.get()
        selected = [layer] if layer in RESOURCE_DEFINITIONS else []
        rendered = composite_heatmaps(
            image,
            self.context.heatmap_bundle,
            selected,
            opacity=HEATMAP_OPACITY,
            point_radius=18,
            blur_radius=HEATMAP_BLUR_RADIUS,
        )
        rendered = zoom_crop(rendered, self._zoom_number(), self.zoom_center)

        available_width = max(760, self.map_label.winfo_width() - 20)
        available_height = max(620, self.map_label.winfo_height() - 20)
        rendered.thumbnail(
            (available_width, available_height),
            Image.Resampling.LANCZOS,
        )
        self.ctk_image = ctk.CTkImage(
            light_image=rendered,
            dark_image=rendered,
            size=rendered.size,
        )
        self.map_label.configure(image=self.ctk_image, text="")
        zoom_text = self.zoom_level.get()
        if zoom_text != "Fit":
            self.map_status.configure(
                text=(
                    f"Map zoom {zoom_text}. Click another point to move the fixed focus. "
                    "Use Show server icons to include or hide Rust+ markers."
                )
            )

    def recommend_starter_spot(self) -> None:
        if self._starter_busy:
            return
        bundle = self.context.heatmap_bundle
        if bundle is None:
            self.map_status.configure(
                text="Load and analyze the current or saved map before requesting a starter spot."
            )
            return

        world_size = self.current_world_size()
        markers = (
            self.context.snapshot.markers
            if self.context.snapshot is not None
            else []
        )
        self._starter_busy = True
        self.starter_button.configure(state="disabled", text="Analyzing map…")
        self.map_status.configure(
            text="Comparing resources, roads, terrain, water, monuments, shops, events, and map-edge risk…"
        )

        def work():
            return recommend_starter_spots(
                bundle,
                world_size,
                markers=markers,
                limit=3,
            )

        def success(spots) -> None:
            self._starter_busy = False
            self.starter_button.configure(state="normal", text="Recommend starter spot")
            self._starter_spots = list(spots)
            if not spots:
                self._set_hotspot_text(
                    "No defensible starter recommendation could be calculated from this map analysis."
                )
                self.map_status.configure(text="Starter-spot analysis found no usable land candidate.")
                return

            best = spots[0]
            self.zoom_center = (best.x_fraction, 1.0 - best.y_fraction)
            self.zoom_level.set("3x")
            self.render_map()
            lines = [
                "RECOMMENDED STARTER BUILDING SPOTS",
                "",
                "These are map-suitability estimates, not guarantees of player safety.",
                "",
            ]
            for index, spot in enumerate(spots, start=1):
                lines.append(f"{index}. {spot.grid} · {spot.score}/100")
                for reason in spot.reasons:
                    lines.append(f"   + {reason}")
                for caution in spot.cautions:
                    lines.append(f"   ! {caution}")
                lines.append("")
            self._set_hotspot_text("\n".join(lines).rstrip())
            self.map_status.configure(
                text=(
                    f"Best starter recommendation: {best.grid} ({best.score}/100). "
                    "The map is fixed at 3x zoom on that area; reasons are listed on the right."
                )
            )

        def error(exc: Exception) -> None:
            self._starter_busy = False
            self.starter_button.configure(state="normal", text="Recommend starter spot")
            self.map_status.configure(text=f"Starter-spot analysis failed: {exc}")

        run_in_worker(self, work, success, error)
