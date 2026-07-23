from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
import time
import traceback
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox
from typing import Any, Callable, Iterable, Sequence

import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from rust_companion_plus.config import APP_DATA_DIR
from rust_companion_plus.services.deal_notifications import (
    DealAlert,
    NOTIFICATION_SETTINGS_KEY,
    normalize_notification_settings,
)
from rust_companion_plus.services.rustplus_client import ServerSnapshot
from rust_companion_plus.services import builtin_map_analyzer as _builtin_map_analyzer
from rust_companion_plus.services import resource_heatmaps as _resource_heatmaps
from rust_companion_plus.services import shop_value as _shop_value
from rust_companion_plus.services.resource_heatmaps import grid_reference
from rust_companion_plus.ui import common as _ui_common
from rust_companion_plus.ui.notifications import show_windows_notification
from rust_companion_plus.ui.tabs import map_enhanced as _map_enhanced
from rust_companion_plus.ui.tabs import map_tab as _map_tab
from rust_companion_plus.ui.tabs import shops as _shops_base
from rust_companion_plus.ui.tabs import shops_enhanced as _shops_enhanced


HOTFIX_ID = "MAP_CLICK_DRONE_SHOPS_ERROR_NOTIFICATIONS_V3"
MARKER_HIT_RADIUS_PX = 34.0
CLICK_DRAG_THRESHOLD_PX = 7.0
HEATMAP_RENDER_OPACITY = 0.72

# These are conservative decision-support references, not claims about a fixed
# NPC vendor price. They prevent strategically useful, noncraftable components
# from being rated only by a temporarily weak or uniform player market.
STRATEGIC_SCRAP_REFERENCES: dict[str, float] = {
    "cctv camera": 100.0,
}
STRATEGIC_GOOD_VALUE_DISCOUNT = 0.30
STRATEGIC_SCORE_FLOOR = 76


def _normalized_name(value: Any) -> str:
    normalizer = getattr(_shop_value, "_normalized_name", None)
    if callable(normalizer):
        return str(normalizer(value))
    return " ".join(str(value or "").casefold().split())


def strategic_scrap_reference(item_name: Any, currency_name: Any) -> float:
    """Return the curated utility reference for an exact Scrap market."""
    if _normalized_name(currency_name) != "scrap":
        return 0.0
    return float(STRATEGIC_SCRAP_REFERENCES.get(_normalized_name(item_name), 0.0))


_ORIGINAL_SCORE_SHOP_ROWS = getattr(
    _shop_value,
    "_strategic_reference_original_score_shop_rows",
    _shop_value.score_shop_rows,
)


def score_shop_rows_with_strategic_references(
    rows: Sequence[Any],
    history: Any = None,
):
    """Apply a conservative strategic floor after normal peer/history scoring."""
    scored, updated_history = _ORIGINAL_SCORE_SHOP_ROWS(rows, history)
    adjusted = []
    label_rank = {
        "CAN'T MISS": 6,
        "STEAL": 5,
        "GOOD VALUE": 4,
        "FAIR": 3,
        "UNPRICED": 2,
        "OVERPRICED": 1,
        "OUT OF STOCK": 0,
    }

    for item in scored:
        row = item.row
        deal = item.deal
        reference = strategic_scrap_reference(
            getattr(row, "item_name", ""),
            getattr(row, "currency_name", ""),
        )
        stock = int(getattr(row, "stock", 0) or 0)
        is_blueprint = bool(getattr(row, "item_is_blueprint", False))
        unit_cost = float(getattr(deal, "unit_cost", 0.0) or 0.0)
        strategic_discount = (
            (reference - unit_cost) / reference
            if reference > 0.0
            else 0.0
        )
        cheapest_or_tied = int(getattr(deal, "peer_rank", 1) or 1) <= 1

        should_lift = (
            reference > 0.0
            and stock > 0
            and not is_blueprint
            and cheapest_or_tied
            and strategic_discount >= STRATEGIC_GOOD_VALUE_DISCOUNT
            and label_rank.get(str(deal.label), 0) < label_rank["GOOD VALUE"]
        )
        if not should_lift:
            adjusted.append(item)
            continue

        score_floor = min(
            79,
            STRATEGIC_SCORE_FLOOR
            + max(0, round((strategic_discount - 0.50) * 10)),
        )
        reason = (
            f"{round(strategic_discount * 100):.0f}% below the curated "
            f"{reference:g}-Scrap strategic utility reference for "
            f"{getattr(row, 'item_name', 'this item')}. This floor can raise "
            "a cheapest or tied listing to GOOD VALUE, but live peers/history "
            f"are still required for STEAL alerts. {deal.reason}"
        )
        lifted_deal = replace(
            deal,
            score=max(int(deal.score), score_floor),
            label="GOOD VALUE",
            benchmark=max(float(deal.benchmark), reference),
            discount_fraction=max(
                float(deal.discount_fraction),
                round(strategic_discount, 6),
            ),
            reason=reason,
            alert_level="",
            actionable=True,
            item_tier=max(2, int(deal.item_tier)),
            item_tier_name=(
                deal.item_tier_name
                if int(deal.item_tier) >= 2
                else "Mid tier"
            ),
        )
        adjusted.append(replace(item, deal=lifted_deal))

    return adjusted, updated_history


def marker_fraction_candidates(
    x: Any,
    y: Any,
    map_size: Any,
) -> tuple[tuple[float, float], ...]:
    """Return top-left image fractions for Rust+ map coordinates.

    Current Rust+ marker and team coordinates use the 0..map-size convention.
    Negative values are accepted as a compatibility fallback for centered-world
    payloads emitted by older integrations.
    """
    try:
        numeric_x = float(x)
        numeric_y = float(y)
        numeric_size = float(map_size)
    except (TypeError, ValueError):
        return ()
    if (
        numeric_size <= 0
        or not math.isfinite(numeric_x)
        or not math.isfinite(numeric_y)
    ):
        return ()

    if numeric_x < 0.0 or numeric_y < 0.0:
        half = numeric_size / 2.0
        x_fraction = (numeric_x + half) / numeric_size
        world_y_fraction = (numeric_y + half) / numeric_size
    else:
        x_fraction = numeric_x / numeric_size
        world_y_fraction = numeric_y / numeric_size

    if not (
        -0.02 <= x_fraction <= 1.02
        and -0.02 <= world_y_fraction <= 1.02
    ):
        return ()
    return ((
        min(1.0, max(0.0, x_fraction)),
        min(1.0, max(0.0, 1.0 - world_y_fraction)),
    ),)


def marker_screen_position(
    fraction: tuple[float, float],
    source_size: tuple[int, int],
    crop_box: tuple[int, int, int, int],
    output_size: tuple[int, int],
    label_size: tuple[int, int],
) -> tuple[float, float] | None:
    """Project one map fraction into the centered CTkLabel image rectangle."""
    source_width, source_height = source_size
    left, top, right, bottom = crop_box
    crop_width = max(1, right - left)
    crop_height = max(1, bottom - top)
    source_x = float(fraction[0]) * max(1, source_width - 1)
    source_y = float(fraction[1]) * max(1, source_height - 1)
    if not (left <= source_x <= right and top <= source_y <= bottom):
        return None

    output_width, output_height = output_size
    label_width, label_height = label_size
    offset_x = max(0.0, (label_width - output_width) / 2.0)
    offset_y = max(0.0, (label_height - output_height) / 2.0)
    return (
        offset_x + (source_x - left) / crop_width * output_width,
        offset_y + (source_y - top) / crop_height * output_height,
    )


def find_clicked_marker(
    markers: Iterable[dict[str, Any]],
    *,
    click: tuple[float, float],
    map_size: int,
    source_size: tuple[int, int],
    crop_box: tuple[int, int, int, int],
    output_size: tuple[int, int],
    label_size: tuple[int, int],
    radius: float = MARKER_HIT_RADIUS_PX,
) -> tuple[dict[str, Any], tuple[float, float], float] | None:
    """Return the nearest visible marker and the coordinate interpretation used."""
    best: tuple[dict[str, Any], tuple[float, float], float] | None = None
    click_x, click_y = click
    for marker in markers:
        if not isinstance(marker, dict):
            continue
        for fraction in marker_fraction_candidates(
            marker.get("x"), marker.get("y"), map_size
        ):
            screen = marker_screen_position(
                fraction,
                source_size,
                crop_box,
                output_size,
                label_size,
            )
            if screen is None:
                continue
            distance = math.hypot(screen[0] - click_x, screen[1] - click_y)
            if distance <= radius and (best is None or distance < best[2]):
                best = (marker, fraction, distance)
    return best


def _bundle_layer_count(bundle: Any, resource: str) -> tuple[int, int]:
    points = getattr(bundle, "points", {}) if bundle is not None else {}
    rasters = getattr(bundle, "raster_layers", {}) if bundle is not None else {}
    point_count = len(points.get(resource, []) or []) if isinstance(points, dict) else 0
    raster_count = len(rasters.get(resource, []) or []) if isinstance(rasters, dict) else 0
    return point_count, raster_count


def _read_visible_mask(path: Path, size: tuple[int, int]) -> Image.Image | None:
    try:
        with Image.open(path) as source:
            rgba = source.convert("RGBA").resize(size, Image.Resampling.BILINEAR)
    except (OSError, ValueError):
        return None

    gray = ImageOps.grayscale(rgba)
    alpha = rgba.getchannel("A")
    if alpha.getextrema() != (255, 255):
        gray = ImageChops.lighter(gray, alpha)
    low, high = gray.getextrema()
    if high <= 0:
        return None
    if high > low:
        gray = ImageOps.autocontrast(gray, cutoff=1)
    return gray.point(
        lambda value: 0
        if value < 5
        else min(255, max(64, int(value * 1.45)))
    )


def _point_mask(bundle: Any, resource: str, size: tuple[int, int]) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 0)
    points = getattr(bundle, "points", {}) if bundle is not None else {}
    rows = points.get(resource, []) if isinstance(points, dict) else []
    if not rows:
        return mask
    draw = ImageDraw.Draw(mask)
    radius = max(8, min(28, int(round(min(size) * 0.018))))
    for point in rows:
        try:
            x_fraction = float(getattr(point, "x_fraction"))
            y_fraction = float(getattr(point, "y_fraction"))
            weight = float(getattr(point, "weight", 1.0) or 1.0)
        except (TypeError, ValueError, AttributeError):
            continue
        x = int(min(1.0, max(0.0, x_fraction)) * max(1, width - 1))
        y = int((1.0 - min(1.0, max(0.0, y_fraction))) * max(1, height - 1))
        strength = max(90, min(255, int(145 * max(0.1, weight))))
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=strength,
        )
    return mask.filter(ImageFilter.GaussianBlur(max(4, radius * 0.75)))


def build_visible_heatmap_mask(
    bundle: Any,
    resource: str,
    size: tuple[int, int],
) -> Image.Image:
    """Build a deliberately visible mask from parser rasters and point data."""
    mask = Image.new("L", size, 0)
    rasters = getattr(bundle, "raster_layers", {}) if bundle is not None else {}
    paths = rasters.get(resource, []) if isinstance(rasters, dict) else []
    for raw_path in paths or []:
        loaded = _read_visible_mask(Path(raw_path), size)
        if loaded is not None:
            mask = ImageChops.lighter(mask, loaded)
    mask = ImageChops.lighter(mask, _point_mask(bundle, resource, size))
    return mask


def _draw_layer_legend(image: Image.Image, selected: Sequence[str]) -> None:
    if not selected:
        return
    draw = ImageDraw.Draw(image, "RGBA")
    labels = [name for name in selected if name in _resource_heatmaps.RESOURCE_DEFINITIONS]
    if not labels:
        return
    text = "HEATMAP  " + " + ".join(labels)
    box = draw.textbbox((0, 0), text)
    width = min(image.width - 12, max(160, box[2] - box[0] + 34))
    height = max(28, box[3] - box[1] + 14)
    draw.rounded_rectangle(
        (8, 8, 8 + width, 8 + height),
        radius=8,
        fill=(2, 6, 23, 205),
        outline=(255, 255, 255, 145),
        width=1,
    )
    first = labels[0]
    color = tuple(_resource_heatmaps.RESOURCE_DEFINITIONS[first]["color"])
    draw.ellipse((17, 16, 28, 27), fill=(*color, 255))
    draw.text((34, 14), text, fill=(255, 255, 255, 255))


def composite_visible_heatmaps(
    base_image: Image.Image,
    bundle: Any,
    selected_resources: Iterable[str],
    *,
    opacity: float = HEATMAP_RENDER_OPACITY,
) -> tuple[Image.Image, dict[str, tuple[int, int]]]:
    """Composite high-contrast heatmaps and return per-layer source counts."""
    result = base_image.convert("RGBA")
    selected = [
        resource
        for resource in selected_resources
        if resource in _resource_heatmaps.RESOURCE_DEFINITIONS
    ]
    diagnostics: dict[str, tuple[int, int]] = {}
    for resource in selected:
        diagnostics[resource] = _bundle_layer_count(bundle, resource)
        mask = build_visible_heatmap_mask(bundle, resource, result.size)
        if mask.getbbox() is None:
            continue
        color = tuple(_resource_heatmaps.RESOURCE_DEFINITIONS[resource]["color"])
        alpha = mask.point(
            lambda value: int(value * min(0.90, max(0.15, float(opacity))))
        )
        layer = Image.new("RGBA", result.size, (*color, 0))
        layer.putalpha(alpha)
        result = Image.alpha_composite(result, layer)
    _draw_layer_legend(result, selected)
    return result, diagnostics


def marker_visual(marker: dict[str, Any]) -> tuple[tuple[int, int, int], str]:
    """Return a visible app-side icon color and one-character symbol."""
    name = str(marker.get("name") or "").casefold()
    marker_type = int(marker.get("type", 0) or 0)
    if marker.get("_team_member"):
        return (56, 189, 248), "T"
    if marker_type == 3 or bool(marker.get("sell_orders")):
        return (34, 197, 94), "$"
    if "mission" in name:
        return (168, 85, 247), "M"
    if "cargo" in name or "ship" in name:
        return (249, 115, 22), "C"
    if "patrol" in name or "heli" in name:
        return (239, 68, 68), "H"
    if "bradley" in name or "tank" in name:
        return (220, 38, 38), "B"
    if "crate" in name or "event" in name:
        return (250, 204, 21), "!"
    symbol = str(abs(marker_type) % 10) if marker_type else "•"
    return (251, 146, 60), symbol


def render_server_markers(
    base_image: Image.Image,
    markers: Iterable[dict[str, Any]],
    map_size: int,
) -> tuple[Image.Image, list[dict[str, Any]]]:
    """Draw Rust+ markers ourselves so icon visibility never depends on get_map."""
    result = base_image.convert("RGBA")
    if map_size <= 0:
        return result, []
    draw = ImageDraw.Draw(result, "RGBA")
    radius = max(9, min(18, int(round(min(result.size) * 0.013))))
    rendered: list[dict[str, Any]] = []
    for marker in markers:
        if not isinstance(marker, dict):
            continue
        candidates = marker_fraction_candidates(
            marker.get("x"), marker.get("y"), map_size
        )
        if not candidates:
            continue
        fraction = candidates[0]
        x = int(fraction[0] * max(1, result.width - 1))
        y = int(fraction[1] * max(1, result.height - 1))
        color, symbol = marker_visual(marker)
        draw.ellipse(
            (x - radius + 2, y - radius + 3, x + radius + 2, y + radius + 3),
            fill=(0, 0, 0, 145),
        )
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(*color, 240),
            outline=(255, 255, 255, 245),
            width=max(2, radius // 5),
        )
        text_box = draw.textbbox((0, 0), symbol)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        draw.text(
            (x - text_width / 2, y - text_height / 2 - 1),
            symbol,
            fill=(255, 255, 255, 255),
            stroke_width=1,
            stroke_fill=(0, 0, 0, 220),
        )
        rendered.append(
            {
                "marker": marker,
                "fraction": fraction,
                "pixel": (x, y),
                "radius": radius,
            }
        )
    return result, rendered


def compose_map_layers(
    clean_map: Image.Image,
    bundle: Any,
    selected_resources: Iterable[str],
    markers: Iterable[dict[str, Any]],
    map_size: int,
    *,
    show_server_icons: bool,
) -> tuple[Image.Image, dict[str, tuple[int, int]], list[dict[str, Any]]]:
    """Compose clean map -> heatmaps -> app-rendered markers in a fixed order."""
    rendered, diagnostics = composite_visible_heatmaps(
        clean_map,
        bundle,
        selected_resources,
    )
    marker_positions: list[dict[str, Any]] = []
    if show_server_icons:
        rendered, marker_positions = render_server_markers(
            rendered,
            markers,
            map_size,
        )
    return rendered, diagnostics, marker_positions


def _marker_title(marker: dict[str, Any]) -> str:
    name = str(marker.get("name") or "").strip()
    if marker.get("_team_member"):
        return name or "Team member"
    if int(marker.get("type", 0) or 0) == 3:
        return name or "Vending machine"
    return name or f"Server marker type {int(marker.get('type', 0) or 0)}"


def _marker_detail(
    marker: dict[str, Any],
    fraction: tuple[float, float],
    map_size: int,
) -> str:
    title = _marker_title(marker)
    marker_type = int(marker.get("type", 0) or 0)
    world_y_fraction = 1.0 - fraction[1]
    try:
        grid = grid_reference(
            fraction[0], world_y_fraction, map_size
        )
    except Exception:
        grid = "—"

    kind = (
        "Team member"
        if marker.get("_team_member")
        else "Vending machine"
        if marker_type == 3
        else f"Server icon type {marker_type}"
    )
    lines = [
        title,
        "",
        f"Kind: {kind}",
        f"Grid: {grid}",
        f"World coordinates: {float(marker.get('x', 0) or 0):.0f}, "
        f"{float(marker.get('y', 0) or 0):.0f}",
    ]

    if marker.get("_team_member"):
        lines.append(
            "Status: "
            + ("online" if bool(marker.get("is_online")) else "offline")
            + (", alive" if bool(marker.get("is_alive", True)) else ", dead")
        )

    orders = marker.get("sell_orders") or []
    if marker_type == 3:
        lines.extend(["", f"Sell orders: {len(orders) if isinstance(orders, list) else 0}"])
        if isinstance(orders, list):
            for order in orders[:10]:
                if not isinstance(order, dict):
                    continue
                item = int(order.get("item_id", 0) or 0)
                quantity = int(order.get("quantity", 0) or 0)
                currency = int(order.get("currency_id", 0) or 0)
                cost = int(order.get("cost_per_item", 0) or 0)
                stock = int(order.get("amount_in_stock", 0) or 0)
                item_bp = " BP" if bool(order.get("item_is_blueprint")) else ""
                currency_bp = " BP" if bool(order.get("currency_is_blueprint")) else ""
                lines.append(
                    f"• {quantity} × item {item}{item_bp} for "
                    f"{cost} × item {currency}{currency_bp} · stock {stock}"
                )
            if len(orders) > 10:
                lines.append(f"• …and {len(orders) - 10} more")

    return "\n".join(lines)


def _image_cache_key(image: Image.Image) -> str:
    preview = image.convert("L").resize((64, 64), Image.Resampling.BILINEAR)
    digest = hashlib.sha1(preview.tobytes()).hexdigest()[:14]
    return f"{image.width}x{image.height}-{digest}"


_OriginalMapTab = getattr(
    _map_enhanced,
    "_map_layers_original_class",
    _map_enhanced.MapTab,
)


class ClickableServerMarkerMapTab(_OriginalMapTab):
    """Map implementation with deterministic heatmaps and local server icons."""

    def __init__(self, master: Any, context: Any):
        self._marker_press_origin: tuple[int, int] | None = None
        self._marker_dragged = False
        self._marker_click_job: Any = None
        self._hotfix_map_token: tuple[Any, ...] | None = None
        self._hotfix_auto_icons_done = False
        self._hotfix_marker_positions: list[dict[str, Any]] = []
        self._hotfix_heatmap_diagnostics: dict[str, tuple[int, int]] = {}
        self._hotfix_heatmap_error = ""
        self._hotfix_generated_bundle_key = ""
        super().__init__(master, context)

    def _clean_map_source(self) -> Image.Image | None:
        for image in (
            getattr(self, "map_image_clean", None),
            getattr(self.context, "clean_map_image", None),
            getattr(self.context, "map_image", None),
            getattr(self, "map_image_with_icons", None),
        ):
            if image is not None:
                return image
        return None

    def _base_map_for_render(self) -> Image.Image | None:
        # Never depend on the alternate Rust+ pre-rendered icon image. We add the
        # live marker layer ourselves after heatmaps so both toggles are reliable.
        return self._clean_map_source()

    def _manifest_markers(self) -> list[dict[str, Any]]:
        source = str(getattr(self, "current_source_path", "") or "").strip()
        if not source:
            return []
        path = Path(source) / "map_resolved.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return []
        rows = payload.get("markers") if isinstance(payload, dict) else []
        return [dict(row) for row in rows or [] if isinstance(row, dict)]

    def _clickable_markers(self) -> list[dict[str, Any]]:
        snapshot = getattr(self.context, "snapshot", None)
        markers = [
            dict(marker)
            for marker in (getattr(snapshot, "markers", None) or [])
            if isinstance(marker, dict)
        ]
        if not markers:
            markers = self._manifest_markers()
        for member in getattr(snapshot, "team", None) or []:
            if not isinstance(member, dict):
                continue
            if member.get("x") is None or member.get("y") is None:
                continue
            row = dict(member)
            row["_team_member"] = True
            row["type"] = -100
            row["name"] = str(member.get("name") or "Team member")
            markers.append(row)
        return markers

    def _heatmap_source_path(self) -> Path | None:
        current = str(getattr(self, "current_source_path", "") or "").strip()
        if current:
            return Path(current)
        record = getattr(self.context, "profile_record", {})
        assets = record.get("assets") if isinstance(record, dict) else {}
        parsed = str(assets.get("parsed_map_dir") or "").strip() if isinstance(assets, dict) else ""
        return Path(parsed) if parsed else None

    @staticmethod
    def _bundle_has_layers(bundle: Any, selected: Sequence[str]) -> bool:
        if bundle is None:
            return False
        return all(sum(_bundle_layer_count(bundle, name)) > 0 for name in selected)

    def _resolve_heatmap_bundle(
        self,
        selected: Sequence[str],
        image: Image.Image,
    ) -> Any:
        bundle = getattr(self.context, "heatmap_bundle", None)
        if not selected or self._bundle_has_layers(bundle, selected):
            return bundle

        source = self._heatmap_source_path()
        if source is not None and source.exists():
            try:
                loaded = _resource_heatmaps.load_heatmap_bundle(
                    source,
                    int(self.current_world_size() or 0),
                )
            except Exception as exc:
                self._hotfix_heatmap_error = f"Could not reload map layers: {exc}"
            else:
                if self._bundle_has_layers(loaded, selected):
                    self.context.heatmap_bundle = loaded
                    self._hotfix_heatmap_error = ""
                    return loaded

        cache_key = _image_cache_key(image)
        if cache_key == self._hotfix_generated_bundle_key and bundle is not None:
            return bundle

        output = (
            source / "_visual_layers_v2"
            if source is not None
            else APP_DATA_DIR / "heatmap_render_cache" / cache_key
        )
        try:
            _builtin_map_analyzer.analyze_map_image(
                image,
                output,
                world_size=int(self.current_world_size() or 0),
                markers=self._clickable_markers(),
            )
            generated = _resource_heatmaps.load_heatmap_bundle(
                output,
                int(self.current_world_size() or 0),
            )
        except Exception as exc:
            self._hotfix_heatmap_error = f"Heatmap fallback analysis failed: {exc}"
            return bundle

        self._hotfix_generated_bundle_key = cache_key
        self.context.heatmap_bundle = generated
        self._hotfix_heatmap_error = ""
        return generated

    @staticmethod
    def _marker_fingerprint(markers: Sequence[dict[str, Any]]) -> tuple[Any, ...]:
        return tuple(
            (
                str(row.get("id") or ""),
                int(row.get("type", 0) or 0),
                round(float(row.get("x", 0) or 0), 2),
                round(float(row.get("y", 0) or 0), 2),
                str(row.get("name") or ""),
                bool(row.get("_team_member")),
            )
            for row in markers
        )

    def _composite_source(self) -> Image.Image | None:
        image = self._clean_map_source()
        if image is None:
            return None
        if getattr(self, "map_image_clean", None) is not None:
            self.context.clean_map_image = self.map_image_clean
        else:
            self.context.clean_map_image = image

        markers = self._clickable_markers()
        map_token = (id(image), image.size)
        if map_token != self._hotfix_map_token:
            self._hotfix_map_token = map_token
            self._hotfix_auto_icons_done = False
            self._invalidate_composite_cache()

        if markers and not self._hotfix_auto_icons_done:
            self.show_server_icons.set(True)
            self._hotfix_auto_icons_done = True

        selected = tuple(self.selected_overlay_layers())
        bundle = self._resolve_heatmap_bundle(selected, image)
        marker_fingerprint = self._marker_fingerprint(markers)
        bundle_signature = tuple(
            (name, *_bundle_layer_count(bundle, name))
            for name in selected
        )
        key = (
            id(image),
            image.size,
            str(getattr(bundle, "source_root", "")),
            bundle_signature,
            selected,
            bool(self.show_server_icons.get()),
            marker_fingerprint,
        )
        if (
            key == self._composite_cache_key
            and self._composite_cache_image is not None
        ):
            return self._composite_cache_image

        rendered, diagnostics, marker_positions = compose_map_layers(
            image,
            bundle,
            selected,
            markers,
            int(self.current_world_size() or 0),
            show_server_icons=bool(self.show_server_icons.get()),
        )
        self._hotfix_heatmap_diagnostics = diagnostics
        self._hotfix_marker_positions = marker_positions
        self._composite_cache_key = key
        self._composite_cache_image = rendered
        self._last_render_signature = None
        return rendered

    def _render(self, *, interactive: bool) -> None:
        super()._render(interactive=interactive)
        selected = self.selected_overlay_layers()
        if selected:
            details = []
            for name in selected:
                point_count, raster_count = self._hotfix_heatmap_diagnostics.get(
                    name, (0, 0)
                )
                details.append(
                    f"{name}: {raster_count} raster / {point_count} points"
                )
            layer_text = "; ".join(details)
        else:
            layer_text = "no heatmap selected"
        icon_text = (
            f"{len(self._hotfix_marker_positions)} app-rendered icons"
            if bool(self.show_server_icons.get())
            else "icons hidden"
        )
        suffix = f" · {self._hotfix_heatmap_error}" if self._hotfix_heatmap_error else ""
        self.map_status.configure(
            text=(
                f"Zoom {self.zoom_level.get()} · {layer_text} · {icon_text}. "
                "Heatmaps and icons are rendered locally on the clean Rust+ map; "
                "click an icon for details, drag to pan, and double-click to recenter."
                f"{suffix}"
            )
        )

    def _pan_start(self, event: Any) -> None:
        self._marker_press_origin = (
            int(getattr(event, "x", 0)),
            int(getattr(event, "y", 0)),
        )
        self._marker_dragged = False
        super()._pan_start(event)

    def _pan_move(self, event: Any) -> None:
        if self._marker_press_origin is not None:
            dx = int(getattr(event, "x", 0)) - self._marker_press_origin[0]
            dy = int(getattr(event, "y", 0)) - self._marker_press_origin[1]
            if math.hypot(dx, dy) >= CLICK_DRAG_THRESHOLD_PX:
                self._marker_dragged = True
        super()._pan_move(event)

    def _pan_end(self, event: Any) -> None:
        click = (
            int(getattr(event, "x", 0)),
            int(getattr(event, "y", 0)),
        )
        should_click = self._marker_press_origin is not None and not self._marker_dragged
        self._marker_press_origin = None
        self._marker_dragged = False
        super()._pan_end(event)
        if should_click:
            if self._marker_click_job is not None:
                try:
                    self.after_cancel(self._marker_click_job)
                except Exception:
                    pass
            self._marker_click_job = self.after(
                180,
                lambda: self._open_marker_at(*click),
            )

    def _focus_clicked_point(self, event: Any) -> None:
        if self._marker_click_job is not None:
            try:
                self.after_cancel(self._marker_click_job)
            except Exception:
                pass
            self._marker_click_job = None
        super()._focus_clicked_point(event)

    def _open_marker_at(self, x: int, y: int) -> None:
        self._marker_click_job = None
        if not bool(self.show_server_icons.get()):
            self.map_status.configure(
                text="Turn on Server icons, then click a shop, event, mission, or team icon."
            )
            return

        source = self._clean_map_source()
        map_size = int(self.current_world_size() or 0)
        markers = self._clickable_markers()
        if source is None or map_size <= 0 or not markers:
            self.map_status.configure(
                text="No live or saved server-marker data is loaded for this map yet. Refresh the server snapshot and map."
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
        hit = find_clicked_marker(
            markers,
            click=(x, y),
            map_size=map_size,
            source_size=source.size,
            crop_box=crop_box,
            output_size=output_size,
            label_size=label_size,
        )
        if hit is None:
            self.map_status.configure(
                text="No server icon was found there. Click closer to the center of an app-rendered icon."
            )
            return

        marker, fraction, _distance = hit
        title = _marker_title(marker)
        self.map_status.configure(text=f"Selected {title}. Click another icon for details.")
        messagebox.showinfo(
            title,
            _marker_detail(marker, fraction, map_size),
            parent=self,
        )




DRONE_FILTER_HELP = (
    "Shows player-owned broadcast vending used by the Drone Marketplace. "
    "Rust+ does not expose whether the same shop also has safe walk-up access."
)
ERROR_REPEAT_SECONDS = 600
ERROR_NOTIFICATION_STORE_KEY = "app_error_notifications_seen_v1"
_ERROR_LAST_SENT: dict[str, float] = {}
_ERROR_LOCK = threading.Lock()
_ACTIVE_APP: Any = None


def _as_positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _marker_type(marker: Any) -> int:
    if not isinstance(marker, dict):
        return 0
    try:
        return int(marker.get("type", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _explicit_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().casefold() in {
        "1", "true", "yes", "on", "drone", "drone-only", "drone only"
    }


def is_drone_marketplace_marker(marker: Any) -> bool:
    """Return whether a Rust+ vending marker is a Drone Marketplace candidate.

    Player-owned broadcast vending machines carry a non-zero owner Steam ID in
    Rust+ marker payloads. Explicit drone flags are accepted for imported or
    future payloads. This intentionally does not claim that walk-up access is
    impossible because the companion protocol does not expose building access.
    """
    if not isinstance(marker, dict):
        return False
    marker_type = _marker_type(marker)
    if marker_type != 3 and not marker.get("sell_orders"):
        return False

    for key in (
        "drone_only",
        "is_drone_only",
        "drone_accessible",
        "is_drone_accessible",
        "delivery_only",
        "marketplace_only",
    ):
        if key in marker and _explicit_true(marker.get(key)):
            return True

    name = " ".join(str(marker.get("name") or "").casefold().split())
    if any(
        token in name
        for token in (
            "drone only",
            "drone-only",
            "drone shop",
            "drone delivery",
            "[drone]",
        )
    ):
        return True

    return _as_positive_int(marker.get("steam_id")) > 0


def filter_drone_marketplace_markers(
    markers: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        dict(marker)
        for marker in markers
        if is_drone_marketplace_marker(marker)
    ]


_OriginalShopsTab = getattr(
    _shops_enhanced,
    "_drone_filter_original_class",
    _shops_enhanced.ShopsTab,
)


class DroneMarketplaceShopsTab(_OriginalShopsTab):
    """Enhanced shop tab with a Drone Marketplace-only view."""

    def __init__(self, master: Any, context: Any):
        self.drone_marketplace_only = ctk.BooleanVar(value=False)
        self._drone_marker_count = 0
        self._all_vending_marker_count = 0
        super().__init__(master, context)

    def _build_filter_bar(self) -> None:
        super()._build_filter_bar()
        try:
            self.filter_tabs.configure(height=126)
        except Exception:
            pass
        simple = self.filter_tabs.tab("Simple")
        self.drone_marketplace_checkbox = ctk.CTkCheckBox(
            simple,
            text="Drone Marketplace shops only",
            variable=self.drone_marketplace_only,
            command=self._drone_filter_changed,
        )
        self.drone_marketplace_checkbox.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            padx=(12, 8),
            pady=(0, 9),
        )
        self.drone_marketplace_hint = ctk.CTkLabel(
            simple,
            text=DRONE_FILTER_HELP,
            text_color=("#64748b", "#94a3b8"),
            anchor="w",
            justify="left",
            wraplength=570,
            font=ctk.CTkFont(size=10),
        )
        self.drone_marketplace_hint.grid(
            row=1,
            column=2,
            columnspan=2,
            sticky="ew",
            padx=(8, 12),
            pady=(0, 9),
        )

    def _drone_filter_changed(self) -> None:
        self._raw_signature = None
        self._scored_rows = []
        self._last_requested_sort = ""
        self.refresh()

    def clear_filters(self) -> None:
        self.drone_marketplace_only.set(False)
        self._raw_signature = None
        self._scored_rows = []
        super().clear_filters()

    def refresh(self) -> None:
        snapshot = getattr(self.context, "snapshot", None)
        if snapshot is None or not bool(self.drone_marketplace_only.get()):
            self._drone_marker_count = 0
            self._all_vending_marker_count = sum(
                1
                for marker in (getattr(snapshot, "markers", None) or [])
                if isinstance(marker, dict)
                and _marker_type(marker) == 3
            )
            super().refresh()
            return

        original_markers = [
            dict(marker)
            for marker in (getattr(snapshot, "markers", None) or [])
            if isinstance(marker, dict)
        ]
        filtered_markers = filter_drone_marketplace_markers(original_markers)
        self._all_vending_marker_count = sum(
            1
            for marker in original_markers
            if _marker_type(marker) == 3
        )
        self._drone_marker_count = len(filtered_markers)
        proxy = ServerSnapshot(
            server=dict(getattr(snapshot, "server", {}) or {}),
            team=[dict(row) for row in (getattr(snapshot, "team", None) or [])],
            markers=filtered_markers,
            server_time=str(getattr(snapshot, "server_time", "") or ""),
        )
        self.context.snapshot = proxy
        try:
            super().refresh()
        finally:
            self.context.snapshot = snapshot

    def _render_scored_rows(self, map_size: int) -> None:
        super()._render_scored_rows(map_size)
        if not bool(self.drone_marketplace_only.get()):
            return
        base_status = str(self.status.cget("text") or "")
        self.status.configure(
            text=(
                f"{base_status} · Drone Marketplace candidates: "
                f"{self._drone_marker_count}/{self._all_vending_marker_count} "
                "broadcast vending marker(s)."
            )
        )


def _error_text(error: Any) -> str:
    if isinstance(error, BaseException):
        text = str(error).strip()
        return text or type(error).__name__
    return str(error or "").strip()


def is_relevant_app_error(category: Any, error: Any) -> bool:
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return False
    text = " ".join(_error_text(error).casefold().split())
    if not text:
        return False
    expected = (
        "operation cancelled",
        "operation canceled",
        "user cancelled",
        "user canceled",
        "no saved analyzed map is available",
        "no active server profile",
        "complete the rust+ credentials",
        "profile incomplete",
        "rust process is not running",
        "rust is not running",
    )
    if any(fragment in text for fragment in expected):
        return False
    category_text = " ".join(str(category or "Application").split())
    return bool(category_text)


def _find_app(owner: Any) -> Any:
    if owner is not None:
        context = getattr(owner, "context", None)
        candidate = getattr(context, "app", None)
        if candidate is not None:
            return candidate
        if hasattr(owner, "deal_notifications") and hasattr(owner, "context"):
            return owner
        try:
            top = owner.winfo_toplevel()
        except Exception:
            top = None
        if top is not None and hasattr(top, "deal_notifications"):
            return top
    return _ACTIVE_APP


def _error_fingerprint(category: str, message: str) -> str:
    return hashlib.sha1(
        f"{category.casefold()}|{message.casefold()}".encode("utf-8", errors="replace")
    ).hexdigest()


def publish_relevant_app_error(
    owner: Any,
    category: Any,
    error: Any,
    *,
    traceback_text: str = "",
) -> bool:
    """Notify once per relevant error signature during a cooldown window."""
    category_text = " ".join(str(category or "Application").split())[:80]
    message = " ".join(_error_text(error).replace("\x00", "").split())[:320]
    if not is_relevant_app_error(category_text, error):
        return False

    fingerprint = _error_fingerprint(category_text, message)
    now = time.monotonic()
    with _ERROR_LOCK:
        previous = _ERROR_LAST_SENT.get(fingerprint, 0.0)
        if previous and now - previous < ERROR_REPEAT_SECONDS:
            return False
        _ERROR_LAST_SENT[fingerprint] = now

    alert = DealAlert(
        fingerprint=f"app-error:{fingerprint}",
        severity=3,
        title=f"Rust Companion+ error · {category_text}"[:90],
        message=(
            f"{message}. The error was recorded in the app timeline and log."
            if not message.endswith((".", "!", "?"))
            else f"{message} The error was recorded in the app timeline and log."
        )[:500],
        label="APP ERROR",
        score=100,
        grid="",
        shop=category_text,
        item_name="",
    )

    app = _find_app(owner)
    delivered = False

    def deliver_through_app() -> None:
        context = getattr(app, "context", None)
        if context is not None:
            try:
                context.record_event(
                    "APP ERROR",
                    f"{category_text}: {message}",
                    "error",
                )
            except Exception:
                pass
            store = getattr(context, "store", None)
            if store is not None:
                try:
                    seen = dict(store.get(ERROR_NOTIFICATION_STORE_KEY, {}) or {})
                    seen[fingerprint] = int(time.time())
                    if len(seen) > 200:
                        seen = dict(list(seen.items())[-200:])
                    store.set(ERROR_NOTIFICATION_STORE_KEY, seen)
                except Exception:
                    pass

        raw_settings = (
            context.store.get(NOTIFICATION_SETTINGS_KEY, {})
            if context is not None and getattr(context, "store", None) is not None
            else {}
        )
        settings = normalize_notification_settings(raw_settings)
        settings["enabled"] = True
        settings["windows_notifications"] = True
        settings["in_app_notifications"] = True
        settings["popup_seconds"] = max(12, int(settings.get("popup_seconds", 15)))
        app.deal_notifications.publish(
            [alert],
            settings=settings,
            on_action=(
                (lambda: app.show_tab("Overview"))
                if callable(getattr(app, "show_tab", None))
                else None
            ),
            action_label="Open Overview",
            force=True,
        )

    if app is not None:
        try:
            if threading.current_thread() is threading.main_thread():
                deliver_through_app()
            else:
                # Tk operations must be marshalled back to the UI thread.
                app.after(0, deliver_through_app)
            delivered = True
        except Exception:
            delivered = False

    if not delivered:
        delivered = show_windows_notification(
            [alert],
            seconds=15,
            sound=True,
        )

    if traceback_text:
        try:
            sys.stderr.write(traceback_text.rstrip() + "\n")
        except Exception:
            pass
    return delivered


_ORIGINAL_RUN_IN_WORKER = getattr(
    _ui_common,
    "_error_notification_original_run_in_worker",
    _ui_common.run_in_worker,
)


def run_in_worker_with_error_notifications(
    owner: Any,
    work: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    def notified_error(error: Exception) -> None:
        label = getattr(work, "__name__", "Background worker").replace("_", " ")
        publish_relevant_app_error(owner, label, error)
        if on_error is not None:
            on_error(error)
        else:
            messagebox.showerror("Rust Companion+", str(error), parent=owner)

    _ORIGINAL_RUN_IN_WORKER(owner, work, on_success, notified_error)


def _install_process_error_hooks() -> None:
    if not getattr(sys, "_rust_companion_error_hook_v3", False):
        original_sys_hook = sys.excepthook

        def sys_hook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
            formatted = "".join(traceback.format_exception(exc_type, exc, tb))
            publish_relevant_app_error(
                None,
                "Unhandled application error",
                exc,
                traceback_text=formatted,
            )
            original_sys_hook(exc_type, exc, tb)

        sys.excepthook = sys_hook
        sys._rust_companion_error_hook_v3 = True

    if hasattr(threading, "excepthook") and not getattr(
        threading, "_rust_companion_error_hook_v3", False
    ):
        original_thread_hook = threading.excepthook

        def thread_hook(args: Any) -> None:
            exc = getattr(args, "exc_value", None)
            exc_type = getattr(args, "exc_type", type(exc))
            tb = getattr(args, "exc_traceback", None)
            formatted = "".join(traceback.format_exception(exc_type, exc, tb))
            publish_relevant_app_error(
                None,
                "Unhandled background thread",
                exc,
                traceback_text=formatted,
            )
            original_thread_hook(args)

        threading.excepthook = thread_hook
        threading._rust_companion_error_hook_v3 = True


_shop_value._strategic_reference_original_score_shop_rows = _ORIGINAL_SCORE_SHOP_ROWS
_shop_value.score_shop_rows = score_shop_rows_with_strategic_references
_shop_value._strategic_reference_hotfix_installed = True
_shops_enhanced.score_shop_rows = score_shop_rows_with_strategic_references

_map_enhanced._map_layers_original_class = _OriginalMapTab
_map_enhanced.MapTab = ClickableServerMarkerMapTab
_map_enhanced._marker_click_hotfix_installed = True
_map_enhanced._map_layers_hotfix_installed = HOTFIX_ID

_shops_enhanced._drone_filter_original_class = _OriginalShopsTab
_shops_enhanced.ShopsTab = DroneMarketplaceShopsTab
_shops_enhanced._drone_filter_hotfix_installed = HOTFIX_ID

_ui_common._error_notification_original_run_in_worker = _ORIGINAL_RUN_IN_WORKER
_ui_common.run_in_worker = run_in_worker_with_error_notifications
for _module in (_map_enhanced, _map_tab, _shops_base, _shops_enhanced):
    if hasattr(_module, "run_in_worker"):
        _module.run_in_worker = run_in_worker_with_error_notifications

_install_process_error_hooks()

# Import after map/shop patching so app.py binds the replacement classes.
from rust_companion_plus import app as _app  # noqa: E402

_OriginalAppInit = getattr(
    _app.RustCompanionApp,
    "_error_notification_original_init",
    _app.RustCompanionApp.__init__,
)
_OriginalAppBackground = getattr(
    _app.RustCompanionApp,
    "_error_notification_original_background",
    _app.RustCompanionApp._background,
)


def _app_init_with_error_notifications(self: Any, *args: Any, **kwargs: Any) -> None:
    global _ACTIVE_APP
    _OriginalAppInit(self, *args, **kwargs)
    _ACTIVE_APP = self


def _app_background_with_error_notifications(
    self: Any,
    work: Callable[[], Any],
    success: Callable[[Any], None],
    failure: Callable[[Exception], None],
) -> None:
    def notified_failure(error: Exception) -> None:
        label = getattr(work, "__name__", "Background refresh").replace("_", " ")
        publish_relevant_app_error(self, label, error)
        failure(error)

    _OriginalAppBackground(self, work, success, notified_failure)


def _report_callback_exception(
    self: Any,
    exc_type: type[BaseException],
    exc: BaseException,
    tb: Any,
) -> None:
    formatted = "".join(traceback.format_exception(exc_type, exc, tb))
    publish_relevant_app_error(
        self,
        "User interface callback",
        exc,
        traceback_text=formatted,
    )


_app.RustCompanionApp._error_notification_original_init = _OriginalAppInit
_app.RustCompanionApp._error_notification_original_background = _OriginalAppBackground
_app.RustCompanionApp.__init__ = _app_init_with_error_notifications
_app.RustCompanionApp._background = _app_background_with_error_notifications
_app.RustCompanionApp.report_callback_exception = _report_callback_exception
_app.RustCompanionApp._error_notification_hotfix_installed = HOTFIX_ID
