from __future__ import annotations

from typing import Any

import customtkinter as ctk
from PIL import Image

from rust_companion_plus.services.resource_heatmaps import (
    RESOURCE_DEFINITIONS,
    composite_heatmaps,
)
from rust_companion_plus.services.starter_spot import (
    recommend_starter_spots,
)
from rust_companion_plus.ui.common import MUTED, run_in_worker
from rust_companion_plus.ui.tabs.map_tab import (
    HEATMAP_BLUR_RADIUS,
    HEATMAP_OPACITY,
    NO_HEATMAP,
    MapTab as BaseMapTab,
)


ZOOM_LEVELS = (
    "Fit",
    "1.5x",
    "2x",
    "3x",
    "4x",
    "6x",
    "8x",
)


def _crop_box(
    size: tuple[int, int],
    zoom: float,
    center: tuple[float, float],
) -> tuple[int, int, int, int]:
    width, height = size
    zoom = max(1.0, float(zoom))
    crop_width = max(32, int(round(width / zoom)))
    crop_height = max(32, int(round(height / zoom)))
    cx = min(1.0, max(0.0, float(center[0]))) * width
    cy = min(1.0, max(0.0, float(center[1]))) * height
    left = int(round(cx - crop_width / 2))
    top = int(round(cy - crop_height / 2))
    left = min(max(0, left), max(0, width - crop_width))
    top = min(max(0, top), max(0, height - crop_height))
    return (
        left,
        top,
        min(width, left + crop_width),
        min(height, top + crop_height),
    )


def zoom_crop(
    image: Image.Image,
    zoom: float,
    center: tuple[float, float],
) -> Image.Image:
    """Compatibility helper used by tests and non-interactive callers."""
    source = image.convert("RGBA")
    if zoom <= 1.0:
        return source.copy()
    return source.crop(
        _crop_box(source.size, zoom, center)
    ).resize(
        source.size,
        Image.Resampling.LANCZOS,
    )


def render_zoomed_view(
    image: Image.Image,
    zoom: float,
    center: tuple[float, float],
    output_size: tuple[int, int],
    *,
    interactive: bool,
) -> Image.Image:
    """Crop once and resize directly to the widget's display size."""
    source = image.convert("RGBA")
    crop = (
        source
        if zoom <= 1.0
        else source.crop(_crop_box(source.size, zoom, center))
    )
    resample = (
        Image.Resampling.BILINEAR
        if interactive
        else Image.Resampling.LANCZOS
    )
    return crop.resize(
        (
            max(1, int(output_size[0])),
            max(1, int(output_size[1])),
        ),
        resample,
    )


def _popular_layers() -> list[str]:
    terms = (
        "sulfur",
        "metal",
        "stone",
        "road",
        "water",
        "monument",
    )
    chosen: list[str] = []
    for term in terms:
        match = next(
            (
                name
                for name in RESOURCE_DEFINITIONS
                if term in name.casefold()
            ),
            None,
        )
        if match and match not in chosen:
            chosen.append(match)
    return chosen[:6]


class MapTab(BaseMapTab):
    """Interactive map with cached overlays and throttled zoom/pan rendering."""

    INTERACTION_FRAME_MS = 16
    QUALITY_DELAY_MS = 160

    def __init__(self, master, context):
        self.zoom_level = ctk.StringVar(value="Fit")
        self.zoom_center = (0.5, 0.5)
        self._starter_busy = False
        self._starter_spots = []
        self._drag_origin: tuple[int, int] | None = None
        self._drag_center = self.zoom_center
        self.overlay_vars: dict[str, ctk.BooleanVar] = {}
        self._composite_cache_key: tuple[Any, ...] | None = None
        self._composite_cache_image: Image.Image | None = None
        self._render_job: Any = None
        self._quality_job: Any = None
        self._last_render_signature: tuple[Any, ...] | None = None
        super().__init__(master, context)

        map_frame = self.map_label.master
        self.map_label.grid_configure(row=1)
        self.map_status.grid_configure(row=2)
        map_frame.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(
            map_frame,
            fg_color="transparent",
        )
        toolbar.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=10,
            pady=(8, 2),
        )
        toolbar.grid_columnconfigure(9, weight=1)

        ctk.CTkLabel(
            toolbar,
            text="Zoom",
            text_color=MUTED,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=0, padx=(0, 4))
        ctk.CTkButton(
            toolbar,
            text="−",
            width=34,
            height=30,
            fg_color="transparent",
            border_width=1,
            command=lambda: self.step_zoom(-1),
        ).grid(row=0, column=1, padx=2)
        self.zoom_menu = ctk.CTkOptionMenu(
            toolbar,
            values=list(ZOOM_LEVELS),
            variable=self.zoom_level,
            width=82,
            height=30,
            command=lambda _value: self.render_map(),
        )
        self.zoom_menu.grid(row=0, column=2, padx=2)
        ctk.CTkButton(
            toolbar,
            text="+",
            width=34,
            height=30,
            command=lambda: self.step_zoom(1),
        ).grid(row=0, column=3, padx=2)
        ctk.CTkButton(
            toolbar,
            text="Fit",
            width=48,
            height=30,
            fg_color="transparent",
            border_width=1,
            command=self.reset_zoom,
        ).grid(row=0, column=4, padx=(2, 8))

        self.toolbar_icons = ctk.CTkSwitch(
            toolbar,
            text="Server icons",
            variable=self.show_server_icons,
            command=self._icons_changed,
        )
        self.toolbar_icons.grid(row=0, column=5, padx=6)

        ctk.CTkButton(
            toolbar,
            text="Clear overlays",
            width=105,
            height=30,
            fg_color="transparent",
            border_width=1,
            command=self.clear_overlay_toggles,
        ).grid(row=0, column=6, padx=5)
        ctk.CTkButton(
            toolbar,
            text="Recommend starter spot",
            width=165,
            height=30,
            command=self.recommend_starter_spot,
        ).grid(row=0, column=7, padx=5)

        overlay_bar = ctk.CTkFrame(
            map_frame,
            fg_color="transparent",
        )
        overlay_bar.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=10,
            pady=(0, 8),
        )
        ctk.CTkLabel(
            overlay_bar,
            text="Quick overlays:",
            text_color=MUTED,
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(side="left", padx=(0, 6))
        for name in _popular_layers():
            variable = ctk.BooleanVar(value=False)
            self.overlay_vars[name] = variable
            ctk.CTkCheckBox(
                overlay_bar,
                text=name,
                variable=variable,
                width=0,
                checkbox_width=16,
                checkbox_height=16,
                command=self.render_map,
            ).pack(side="left", padx=5)

        self.map_label.bind(
            "<MouseWheel>",
            self._mouse_wheel_zoom,
            add="+",
        )
        self.map_label.bind(
            "<ButtonPress-1>",
            self._pan_start,
            add="+",
        )
        self.map_label.bind(
            "<B1-Motion>",
            self._pan_move,
            add="+",
        )
        self.map_label.bind(
            "<ButtonRelease-1>",
            self._pan_end,
            add="+",
        )
        self.map_label.bind(
            "<Double-1>",
            self._focus_clicked_point,
            add="+",
        )
        self.map_label.bind(
            "<Button-4>",
            lambda _event: self.step_zoom(1),
            add="+",
        )
        self.map_label.bind(
            "<Button-5>",
            lambda _event: self.step_zoom(-1),
            add="+",
        )
        self.map_label.bind(
            "<Configure>",
            lambda _event: self._request_render(interactive=True),
            add="+",
        )

    def _icons_changed(self) -> None:
        self._invalidate_composite_cache()
        self.render_map()

    def _zoom_number(self) -> float:
        raw = (
            self.zoom_level.get()
            .strip()
            .casefold()
            .removesuffix("x")
        )
        if raw == "fit":
            return 1.0
        try:
            return max(1.0, float(raw))
        except ValueError:
            return 1.0

    def step_zoom(self, direction: int) -> None:
        current_value = self.zoom_level.get()
        current = (
            ZOOM_LEVELS.index(current_value)
            if current_value in ZOOM_LEVELS
            else 0
        )
        target = min(
            len(ZOOM_LEVELS) - 1,
            max(0, current + int(direction)),
        )
        if target == current:
            return
        self.zoom_level.set(ZOOM_LEVELS[target])
        self._request_render(interactive=True)

    def reset_zoom(self) -> None:
        self.zoom_level.set("Fit")
        self.zoom_center = (0.5, 0.5)
        self.render_map()

    def clear_overlay_toggles(self) -> None:
        for variable in self.overlay_vars.values():
            variable.set(False)
        self.active_layer.set(NO_HEATMAP)
        self._invalidate_composite_cache()
        self.render_map()

    def selected_overlay_layers(self) -> list[str]:
        selected = [
            name
            for name, variable in self.overlay_vars.items()
            if variable.get()
        ]
        active = self.active_layer.get()
        if (
            active in RESOURCE_DEFINITIONS
            and active not in selected
        ):
            selected.append(active)
        return selected

    def _mouse_wheel_zoom(self, event: Any) -> None:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta:
            self.step_zoom(1 if delta > 0 else -1)

    def _pan_start(self, event: Any) -> None:
        self._drag_origin = (
            int(getattr(event, "x", 0)),
            int(getattr(event, "y", 0)),
        )
        self._drag_center = self.zoom_center

    def _pan_move(self, event: Any) -> None:
        if self._drag_origin is None:
            return
        zoom = self._zoom_number()
        if zoom <= 1.0:
            return
        width = max(1, int(self.map_label.winfo_width()))
        height = max(1, int(self.map_label.winfo_height()))
        dx = int(getattr(event, "x", 0)) - self._drag_origin[0]
        dy = int(getattr(event, "y", 0)) - self._drag_origin[1]
        self.zoom_center = (
            min(
                1.0,
                max(
                    0.0,
                    self._drag_center[0]
                    - dx / (width * zoom),
                ),
            ),
            min(
                1.0,
                max(
                    0.0,
                    self._drag_center[1]
                    - dy / (height * zoom),
                ),
            ),
        )
        self._request_render(interactive=True)

    def _pan_end(self, _event: Any) -> None:
        self._drag_origin = None
        self._drag_center = self.zoom_center
        self._schedule_quality_render()

    def _focus_clicked_point(self, event: Any) -> None:
        width = max(1, int(self.map_label.winfo_width()))
        height = max(1, int(self.map_label.winfo_height()))
        zoom = self._zoom_number()
        visible_fraction = 1.0 / max(1.0, zoom)
        x_offset = (
            float(getattr(event, "x", 0)) / width - 0.5
        ) * visible_fraction
        y_offset = (
            float(getattr(event, "y", 0)) / height - 0.5
        ) * visible_fraction
        self.zoom_center = (
            min(1.0, max(0.0, self.zoom_center[0] + x_offset)),
            min(1.0, max(0.0, self.zoom_center[1] + y_offset)),
        )
        if zoom <= 1.0:
            self.zoom_level.set("2x")
        self._request_render(interactive=True)

    def _invalidate_composite_cache(self) -> None:
        self._composite_cache_key = None
        self._composite_cache_image = None
        self._last_render_signature = None

    def _composite_source(self) -> Image.Image | None:
        image = self._base_map_for_render()
        if image is None:
            return None

        if self.map_image_clean is not None:
            self.context.clean_map_image = self.map_image_clean
        else:
            self.context.clean_map_image = image

        selected = tuple(self.selected_overlay_layers())
        key = (
            id(image),
            image.size,
            id(self.context.heatmap_bundle),
            selected,
            bool(self.show_server_icons.get()),
        )
        if (
            key == self._composite_cache_key
            and self._composite_cache_image is not None
        ):
            return self._composite_cache_image

        if selected:
            rendered = composite_heatmaps(
                image,
                self.context.heatmap_bundle,
                selected,
                opacity=HEATMAP_OPACITY,
                point_radius=18,
                blur_radius=HEATMAP_BLUR_RADIUS,
            )
        else:
            rendered = image.convert("RGBA")

        self._composite_cache_key = key
        self._composite_cache_image = rendered
        self._last_render_signature = None
        return rendered

    def _display_size(
        self,
        source_size: tuple[int, int],
    ) -> tuple[int, int]:
        available_width = max(
            320,
            int(self.map_label.winfo_width()) - 20,
        )
        available_height = max(
            280,
            int(self.map_label.winfo_height()) - 20,
        )
        width, height = source_size
        scale = min(
            available_width / max(1, width),
            available_height / max(1, height),
        )
        return (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )

    def _request_render(self, *, interactive: bool) -> None:
        if self._render_job is None:
            self._render_job = self.after(
                self.INTERACTION_FRAME_MS,
                lambda: self._run_requested_render(interactive),
            )
        self._schedule_quality_render()

    def _run_requested_render(self, interactive: bool) -> None:
        self._render_job = None
        self._render(interactive=interactive)

    def _schedule_quality_render(self) -> None:
        if self._quality_job is not None:
            try:
                self.after_cancel(self._quality_job)
            except Exception:
                pass
        self._quality_job = self.after(
            self.QUALITY_DELAY_MS,
            self._render_quality,
        )

    def _render_quality(self) -> None:
        self._quality_job = None
        self._render(interactive=False)

    def render_map(self) -> None:
        self._render(interactive=False)

    def _render(self, *, interactive: bool) -> None:
        source = self._composite_source()
        if source is None:
            return

        output_size = self._display_size(source.size)
        signature = (
            self._composite_cache_key,
            self.zoom_level.get(),
            round(self.zoom_center[0], 5),
            round(self.zoom_center[1], 5),
            output_size,
            interactive,
        )
        if signature == self._last_render_signature:
            return

        rendered = render_zoomed_view(
            source,
            self._zoom_number(),
            self.zoom_center,
            output_size,
            interactive=interactive,
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
        self._last_render_signature = signature

        selected = self.selected_overlay_layers()
        layer_text = (
            ", ".join(selected)
            if selected
            else "base map"
        )
        self.map_status.configure(
            text=(
                f"Zoom {self.zoom_level.get()} · {layer_text} · "
                f"server icons {'shown' if self.show_server_icons.get() else 'hidden'}. "
                "Cached overlays keep wheel zoom responsive; drag pans and "
                "double-click recenters."
            )
        )

    def recommend_starter_spot(self) -> None:
        if self._starter_busy:
            return
        bundle = self.context.heatmap_bundle
        if bundle is None:
            self.map_status.configure(
                text=(
                    "Load and analyze the current or saved map before "
                    "requesting a starter spot."
                )
            )
            return

        world_size = self.current_world_size()
        markers = (
            self.context.snapshot.markers
            if self.context.snapshot is not None
            else []
        )
        self._starter_busy = True
        self.map_status.configure(
            text=(
                "Comparing mainland access, buildable land, resources, roads, "
                "terrain, water, monuments, shops, events, and map-edge risk…"
            )
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
            self._starter_spots = list(spots)
            if not spots:
                self._set_hotspot_text(
                    "No practical mainland starter recommendation could be calculated."
                )
                return
            best = spots[0]
            self.zoom_center = (
                best.x_fraction,
                1.0 - best.y_fraction,
            )
            self.zoom_level.set("4x")
            self._request_render(interactive=True)
            lines = [
                "RECOMMENDED STARTER BUILDING SPOTS",
                "",
                (
                    "Remote islands and water-locked cells are filtered out. "
                    "Results remain suitability estimates, not player-safety guarantees."
                ),
                "",
            ]
            for index, spot in enumerate(spots, start=1):
                lines.append(
                    f"{index}. {spot.grid} · {spot.score}/100"
                )
                lines.extend(
                    f"   + {reason}"
                    for reason in spot.reasons
                )
                lines.extend(
                    f"   ! {caution}"
                    for caution in spot.cautions
                )
                lines.append("")
            self._set_hotspot_text(
                "\n".join(lines).rstrip()
            )

        def error(exc: Exception) -> None:
            self._starter_busy = False
            self.map_status.configure(
                text=f"Starter-spot analysis failed: {exc}"
            )

        run_in_worker(self, work, success, error)
