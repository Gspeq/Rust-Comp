from __future__ import annotations

import math
import queue
import threading
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Sequence

from PIL import Image, ImageDraw

from rust_companion_plus import hotfix_map_shop as _legacy
from rust_companion_plus import app as _app
from rust_companion_plus.services import resource_heatmaps as _heatmaps
from rust_companion_plus.services.starter_spot import (
    StarterSpot,
    recommend_starter_spots,
)
from rust_companion_plus.ui.tabs import map_enhanced as _map_enhanced
from rust_companion_plus.ui.tabs import shops_enhanced as _shops_enhanced


HOTFIX_ID = "MAP_CLICK_AND_STARTER_SPOT_V4_1"
CLICK_RADIUS_PX = 52.0
WORKER_POLL_MS = 50
STARTER_LAYER_NAMES = (
    "Stone",
    "Metal",
    "Road Access",
    "Temperate Biome",
    "Sulfur",
    "Water",
    "Monument Proximity",
    "Rough Terrain",
    "Snow Biome",
    "Coastline",
)


def event_coordinates_in_widget(event: Any, target: Any) -> tuple[int, int]:
    """Convert a Tk event from a CTkLabel child into target-widget coordinates.

    CustomTkinter labels contain a canvas and an inner tkinter.Label. Their event
    x/y values are relative to whichever child received the click, not necessarily
    the outer CTkLabel used for map layout and letterboxing calculations.
    """
    try:
        target_root_x = float(target.winfo_rootx())
        target_root_y = float(target.winfo_rooty())
    except Exception:
        target_root_x = 0.0
        target_root_y = 0.0

    try:
        root_x = float(getattr(event, "x_root"))
        root_y = float(getattr(event, "y_root"))
    except (TypeError, ValueError, AttributeError):
        widget = getattr(event, "widget", None)
        try:
            root_x = float(widget.winfo_rootx()) + float(getattr(event, "x", 0) or 0)
            root_y = float(widget.winfo_rooty()) + float(getattr(event, "y", 0) or 0)
        except Exception:
            root_x = target_root_x + float(getattr(event, "x", 0) or 0)
            root_y = target_root_y + float(getattr(event, "y", 0) or 0)

    return (
        int(round(root_x - target_root_x)),
        int(round(root_y - target_root_y)),
    )


def _event_proxy(event: Any, x: int, y: int) -> Any:
    """Return a lightweight event carrying normalized map-label coordinates."""
    return SimpleNamespace(
        x=int(x),
        y=int(y),
        x_root=getattr(event, "x_root", x),
        y_root=getattr(event, "y_root", y),
        delta=getattr(event, "delta", 0),
        widget=getattr(event, "widget", None),
    )


def run_tk_worker(
    owner: Any,
    work: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[Exception], None],
    *,
    poll_ms: int = WORKER_POLL_MS,
) -> None:
    """Run work off-thread while all Tk calls remain on the Tk main thread."""
    results: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def target() -> None:
        try:
            value = work()
        except Exception as exc:  # pragma: no cover - exercised through callback
            results.put(("error", exc))
        else:
            results.put(("success", value))

    def poll() -> None:
        try:
            kind, payload = results.get_nowait()
        except queue.Empty:
            try:
                owner.after(max(10, int(poll_ms)), poll)
            except Exception:
                return
            return
        if kind == "success":
            on_success(payload)
        else:
            on_error(payload)

    # This first call occurs inside the button callback on Tk's main thread.
    owner.after(max(10, int(poll_ms)), poll)
    threading.Thread(target=target, daemon=True).start()


def _mask_values(bundle: Any, resource: str, resolution: int) -> list[int]:
    if bundle is None or resource not in _heatmaps.RESOURCE_DEFINITIONS:
        return [0] * (resolution * resolution)
    mask = _heatmaps.build_resource_mask(
        bundle,
        resource,
        (resolution, resolution),
        point_radius=max(2, resolution // 34),
        blur_radius=max(2, resolution // 22),
    ).convert("L")
    return list(mask.getdata())


def relaxed_starter_spots(
    bundle: Any,
    world_size: int,
    *,
    limit: int = 3,
    resolution: int = 72,
) -> list[StarterSpot]:
    """Fallback ranking that always returns the best usable analyzed land cells.

    The normal recommender remains the first choice. This fallback removes its
    strict minimum-score gate so a difficult map still produces a transparent
    best-available recommendation instead of silently returning nothing.
    """
    if bundle is None or int(world_size or 0) <= 0:
        return []
    resolution = max(48, min(96, int(resolution)))
    available = set(getattr(bundle, "resources", []) or [])
    if not available:
        return []

    wanted = tuple(name for name in STARTER_LAYER_NAMES if name in available)
    masks = {name: _mask_values(bundle, name, resolution) for name in wanted}
    if not masks:
        return []

    def value(name: str, index: int) -> float:
        values = masks.get(name)
        return (values[index] / 255.0) if values else 0.0

    candidates: list[tuple[float, int, int, dict[str, float]]] = []
    for py in range(3, resolution - 3):
        for px in range(3, resolution - 3):
            index = py * resolution + px
            evidence = {name: value(name, index) for name in wanted}
            water = evidence.get("Water", 0.0)
            if water >= 0.68:
                continue

            fx = px / (resolution - 1)
            fy = 1.0 - py / (resolution - 1)
            edge = min(fx, fy, 1.0 - fx, 1.0 - fy)
            score = 0.20
            score += evidence.get("Stone", 0.0) * 0.24
            score += evidence.get("Metal", 0.0) * 0.20
            score += evidence.get("Road Access", 0.0) * 0.22
            score += evidence.get("Temperate Biome", 0.0) * 0.08
            score += evidence.get("Sulfur", 0.0) * 0.04
            score -= water * 0.48
            score -= evidence.get("Monument Proximity", 0.0) * 0.22
            score -= evidence.get("Rough Terrain", 0.0) * 0.15
            score -= evidence.get("Snow Biome", 0.0) * 0.08
            score -= evidence.get("Coastline", 0.0) * 0.07
            score += min(0.11, max(0.0, edge) * 0.42)
            candidates.append((score, px, py, evidence))

    candidates.sort(key=lambda row: row[0], reverse=True)
    selected: list[StarterSpot] = []
    separation = 0.13
    for raw_score, px, py, evidence in candidates:
        fx = px / (resolution - 1)
        fy = 1.0 - py / (resolution - 1)
        if any(
            math.hypot(fx - spot.x_fraction, fy - spot.y_fraction) < separation
            for spot in selected
        ):
            continue

        reasons: list[str] = []
        ranked = sorted(
            (
                (evidence.get("Stone", 0.0) * 0.24, "good stone access"),
                (evidence.get("Road Access", 0.0) * 0.22, "road and component access"),
                (evidence.get("Metal", 0.0) * 0.20, "useful metal access"),
                (evidence.get("Temperate Biome", 0.0) * 0.08, "temperate starter climate"),
                (evidence.get("Sulfur", 0.0) * 0.04, "some sulfur potential"),
            ),
            reverse=True,
        )
        for contribution, label in ranked:
            if contribution >= 0.025:
                reasons.append(label)
            if len(reasons) >= 3:
                break
        if not reasons:
            reasons.append("best available buildable area on this analyzed map")

        cautions: list[str] = ["fallback ranking used because no area passed every strict starter rule"]
        if evidence.get("Monument Proximity", 0.0) >= 0.45:
            cautions.append("closer to monument traffic")
        if evidence.get("Rough Terrain", 0.0) >= 0.55:
            cautions.append("rough terrain may complicate building")
        if evidence.get("Water", 0.0) >= 0.35:
            cautions.append("nearby water reduces buildable area")

        score = int(round(max(0.0, min(1.0, raw_score)) * 100))
        selected.append(
            StarterSpot(
                x_fraction=round(fx, 6),
                y_fraction=round(fy, 6),
                score=score,
                grid=_heatmaps.grid_reference(fx, fy, int(world_size)),
                reasons=tuple(reasons),
                cautions=tuple(cautions),
                evidence={
                    name: round(amount, 3)
                    for name, amount in evidence.items()
                    if amount >= 0.05
                },
            )
        )
        if len(selected) >= max(1, int(limit)):
            break
    return selected


_BaseInteractiveMapTab = _map_enhanced.MapTab
_OriginalMapTab = _legacy._OriginalMapTab


class ReliableInteractiveMapTab(_BaseInteractiveMapTab):
    """Map tab with coordinate-correct icon clicks and reliable starter analysis."""

    def __init__(self, master: Any, context: Any):
        self._reliable_press_origin: tuple[int, int] | None = None
        self._reliable_dragged = False
        self._selected_marker_fraction: tuple[float, float] | None = None
        self._selected_marker_title = ""
        self._interaction_overlay_key: tuple[Any, ...] | None = None
        self._interaction_overlay_image: Image.Image | None = None
        super().__init__(master, context)

    def _invalidate_composite_cache(self) -> None:
        super()._invalidate_composite_cache()
        self._interaction_overlay_key = None
        self._interaction_overlay_image = None

    def _composite_source(self) -> Image.Image | None:
        base = super()._composite_source()
        if base is None:
            return None

        spots = tuple(
            (
                round(float(spot.x_fraction), 6),
                round(float(spot.y_fraction), 6),
                int(spot.score),
            )
            for spot in (getattr(self, "_starter_spots", None) or [])
        )
        selected = self._selected_marker_fraction
        key = (
            id(base),
            spots,
            (
                round(selected[0], 6),
                round(selected[1], 6),
            )
            if selected is not None
            else None,
        )
        if key == self._interaction_overlay_key and self._interaction_overlay_image is not None:
            return self._interaction_overlay_image
        if not spots and selected is None:
            return base

        rendered = base.copy().convert("RGBA")
        draw = ImageDraw.Draw(rendered, "RGBA")
        marker_radius = max(13, min(24, int(round(min(rendered.size) * 0.018))))

        if selected is not None:
            x = int(selected[0] * max(1, rendered.width - 1))
            y = int(selected[1] * max(1, rendered.height - 1))
            draw.ellipse(
                (x - marker_radius - 5, y - marker_radius - 5, x + marker_radius + 5, y + marker_radius + 5),
                outline=(255, 255, 255, 255),
                width=4,
            )
            draw.ellipse(
                (x - marker_radius - 1, y - marker_radius - 1, x + marker_radius + 1, y + marker_radius + 1),
                outline=(249, 115, 22, 255),
                width=4,
            )

        for index, (fx, fy, _score) in enumerate(spots, start=1):
            x = int(fx * max(1, rendered.width - 1))
            y = int((1.0 - fy) * max(1, rendered.height - 1))
            radius = marker_radius + 1
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(2, 132, 199, 235),
                outline=(255, 255, 255, 255),
                width=3,
            )
            label = str(index)
            box = draw.textbbox((0, 0), label)
            draw.text(
                (x - (box[2] - box[0]) / 2, y - (box[3] - box[1]) / 2 - 1),
                label,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 230),
            )

        self._interaction_overlay_key = key
        self._interaction_overlay_image = rendered
        return rendered

    def _normalized_event(self, event: Any) -> tuple[Any, tuple[int, int]]:
        point = event_coordinates_in_widget(event, self.map_label)
        return _event_proxy(event, *point), point

    def _pan_start(self, event: Any) -> None:
        normalized, point = self._normalized_event(event)
        self._reliable_press_origin = point
        self._reliable_dragged = False
        _OriginalMapTab._pan_start(self, normalized)

    def _pan_move(self, event: Any) -> None:
        normalized, point = self._normalized_event(event)
        if self._reliable_press_origin is not None:
            if math.hypot(
                point[0] - self._reliable_press_origin[0],
                point[1] - self._reliable_press_origin[1],
            ) >= float(getattr(_legacy, "CLICK_DRAG_THRESHOLD_PX", 7.0)):
                self._reliable_dragged = True
        _OriginalMapTab._pan_move(self, normalized)

    def _pan_end(self, event: Any) -> None:
        normalized, point = self._normalized_event(event)
        should_open = self._reliable_press_origin is not None and not self._reliable_dragged
        self._reliable_press_origin = None
        self._reliable_dragged = False
        _OriginalMapTab._pan_end(self, normalized)
        if should_open:
            # Open immediately. A visible response is more useful than delaying the
            # click to distinguish it from a double-click recenter gesture.
            self._open_marker_at(*point)

    def _focus_clicked_point(self, event: Any) -> None:
        normalized, _point = self._normalized_event(event)
        _OriginalMapTab._focus_clicked_point(self, normalized)

    def _open_marker_at(self, x: int, y: int) -> None:
        if not bool(self.show_server_icons.get()):
            self.show_server_icons.set(True)
            self._invalidate_composite_cache()
            self.render_map()

        source = self._clean_map_source()
        map_size = int(self.current_world_size() or 0)
        markers = self._clickable_markers()
        if source is None or map_size <= 0 or not markers:
            self.map_status.configure(
                text="No server-marker data is loaded. Refresh Rust+ and load the current map first."
            )
            return

        output_size = self._display_size(source.size)
        label_size = (
            max(1, int(self.map_label.winfo_width())),
            max(1, int(self.map_label.winfo_height())),
        )
        zoom = self._zoom_number()
        crop_box = (
            (0, 0, source.size[0], source.size[1])
            if zoom <= 1.0
            else _map_enhanced._crop_box(source.size, zoom, self.zoom_center)
        )
        hit = _legacy.find_clicked_marker(
            markers,
            click=(int(x), int(y)),
            map_size=map_size,
            source_size=source.size,
            crop_box=crop_box,
            output_size=output_size,
            label_size=label_size,
            radius=CLICK_RADIUS_PX,
        )
        if hit is None:
            self.map_status.configure(
                text="No icon selected. Click the center of a visible shop, mission, event, or team marker."
            )
            return

        marker, fraction, _distance = hit
        title = _legacy._marker_title(marker)
        detail = _legacy._marker_detail(marker, fraction, map_size)
        self._selected_marker_fraction = fraction
        self._selected_marker_title = title
        self._interaction_overlay_key = None
        self._interaction_overlay_image = None
        self._last_render_signature = None
        try:
            self._set_hotspot_text("SELECTED MAP ICON\n\n" + detail)
        except Exception:
            pass
        self.map_status.configure(
            text=f"Selected {title}. Its details are shown in the map side panel."
        )
        self.render_map()
        try:
            from tkinter import messagebox

            messagebox.showinfo(title, detail, parent=self)
        except Exception as exc:
            _legacy.publish_relevant_app_error(self, "Map icon details", exc)

    def _present_starter_spots(
        self,
        spots: Sequence[StarterSpot],
        *,
        used_fallback: bool,
    ) -> None:
        self._starter_spots = list(spots)
        if not spots:
            self.map_status.configure(
                text="Starter analysis completed, but this map did not contain a usable analyzed land cell."
            )
            self._set_hotspot_text(
                "No starter recommendation could be produced. Reload and analyze the current map, then try again."
            )
            return

        best = spots[0]
        self.zoom_center = (best.x_fraction, 1.0 - best.y_fraction)
        self.zoom_level.set("4x")
        self._interaction_overlay_key = None
        self._interaction_overlay_image = None
        self._invalidate_composite_cache()
        self._request_render(interactive=True)

        lines = [
            "RECOMMENDED STARTER BUILDING SPOTS",
            "",
            (
                "Best-available fallback ranking was used because no location passed every strict rule."
                if used_fallback
                else "Strict mainland, access, terrain, resource, and traffic checks passed."
            ),
            "",
        ]
        for index, spot in enumerate(spots, start=1):
            lines.append(f"{index}. {spot.grid} · {spot.score}/100")
            lines.extend(f"   + {reason}" for reason in spot.reasons)
            lines.extend(f"   ! {caution}" for caution in spot.cautions)
            lines.append("")
        self._set_hotspot_text("\n".join(lines).rstrip())
        self.map_status.configure(
            text=(
                f"Starter recommendations ready: {', '.join(spot.grid for spot in spots)}. "
                "Numbered blue markers are now drawn on the map; the view is centered on option 1."
            )
        )

    def recommend_starter_spot(self) -> None:
        if self._starter_busy:
            self.map_status.configure(text="Starter-spot analysis is already running…")
            return

        image = self._clean_map_source()
        world_size = int(self.current_world_size() or 0)
        markers = self._clickable_markers()
        if image is None or world_size <= 0:
            self.map_status.configure(
                text="Load and analyze the current map before requesting a starter recommendation."
            )
            return

        self._starter_busy = True
        self.map_status.configure(
            text="Analyzing mainland access, terrain, roads, resources, water, traffic, and map-edge risk…"
        )
        self._set_hotspot_text("Starter-spot analysis is running…")

        def work() -> tuple[Any, list[StarterSpot], bool]:
            bundle = self._resolve_heatmap_bundle(STARTER_LAYER_NAMES, image)
            spots = recommend_starter_spots(
                bundle,
                world_size,
                markers=markers,
                limit=3,
            )
            used_fallback = False
            if not spots:
                spots = relaxed_starter_spots(
                    bundle,
                    world_size,
                    limit=3,
                )
                used_fallback = bool(spots)
            return bundle, list(spots), used_fallback

        def success(payload: tuple[Any, list[StarterSpot], bool]) -> None:
            self._starter_busy = False
            bundle, spots, used_fallback = payload
            if bundle is not None:
                self.context.heatmap_bundle = bundle
            self._present_starter_spots(spots, used_fallback=used_fallback)

        def error(exc: Exception) -> None:
            self._starter_busy = False
            self.map_status.configure(text=f"Starter-spot analysis failed: {exc}")
            self._set_hotspot_text(
                "STARTER-SPOT ANALYSIS ERROR\n\n" + str(exc)
            )
            _legacy.publish_relevant_app_error(self, "Starter-spot analysis", exc)

        run_tk_worker(self, work, success, error)


# Keep the V3 map/shop/error-notification contract intact while layering the V4.1
# interaction implementation over the class actually constructed by app.py.
# Existing tests correctly treat the V3 identifier as ownership of those older
# features, so this module publishes its own separate activation marker.
_legacy.ClickableServerMarkerMapTab = ReliableInteractiveMapTab
_map_enhanced.MapTab = ReliableInteractiveMapTab
_map_enhanced._map_layers_hotfix_installed = _legacy.HOTFIX_ID
_map_enhanced._marker_click_hotfix_installed = True
_map_enhanced._map_interaction_starter_hotfix_installed = HOTFIX_ID
_app.MapTab = ReliableInteractiveMapTab
_app.RustCompanionApp._map_interaction_starter_hotfix_installed = HOTFIX_ID
