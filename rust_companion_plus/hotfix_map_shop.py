from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Iterable, Sequence
from tkinter import messagebox

from rust_companion_plus.services import shop_value as _shop_value
from rust_companion_plus.services.resource_heatmaps import grid_reference
from rust_companion_plus.ui.tabs import map_enhanced as _map_enhanced


HOTFIX_ID = "MAP_MARKER_CLICK_AND_STRATEGIC_VALUE_V1"
MARKER_HIT_RADIUS_PX = 32.0
CLICK_DRAG_THRESHOLD_PX = 7.0

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


_ORIGINAL_SCORE_SHOP_ROWS = _shop_value.score_shop_rows


def score_shop_rows_with_strategic_references(
    rows: Sequence[Any],
    history: Any = None,
):
    """Apply a conservative strategic floor after normal peer/history scoring.

    The floor may lift a cheapest/tied strategic listing to GOOD VALUE, but it
    never creates an urgent alert by itself. Live peers and history still own
    STEAL and CAN'T MISS decisions.
    """
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
    """Return a top-left image fraction for Rust marker coordinates.

    Rust+ markers normally use 0..world-size coordinates. Negative values are
    treated as the centered-world fallback already used by the marketplace map.
    """
    try:
        numeric_x = float(x)
        numeric_y = float(y)
        numeric_size = float(map_size)
    except (TypeError, ValueError):
        return ()
    if numeric_size <= 0 or not math.isfinite(numeric_x) or not math.isfinite(numeric_y):
        return ()

    if numeric_x < 0.0 or numeric_y < 0.0:
        half = numeric_size / 2.0
        x_fraction = (numeric_x + half) / numeric_size
        world_y_fraction = (numeric_y + half) / numeric_size
    else:
        x_fraction = numeric_x / numeric_size
        world_y_fraction = numeric_y / numeric_size

    if not (-0.02 <= x_fraction <= 1.02 and -0.02 <= world_y_fraction <= 1.02):
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
    source_x = float(fraction[0]) * source_width
    source_y = float(fraction[1]) * source_height
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


_BaseMapTab = _map_enhanced.MapTab


class ClickableServerMarkerMapTab(_BaseMapTab):
    """Map hotfix that turns rendered Rust+ icons into selectable targets."""

    def __init__(self, master: Any, context: Any):
        self._marker_press_origin: tuple[int, int] | None = None
        self._marker_dragged = False
        self._marker_click_job: Any = None
        super().__init__(master, context)

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

    def _clickable_markers(self) -> list[dict[str, Any]]:
        snapshot = getattr(self.context, "snapshot", None)
        if snapshot is None:
            return []
        markers = [
            dict(marker)
            for marker in (getattr(snapshot, "markers", None) or [])
            if isinstance(marker, dict)
        ]
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

    def _open_marker_at(self, x: int, y: int) -> None:
        self._marker_click_job = None
        if not bool(self.show_server_icons.get()):
            self.map_status.configure(
                text="Turn on Server icons, then click a shop, event, mission, or team icon."
            )
            return

        source = self._base_map_for_render()
        map_size = int(self.current_world_size() or 0)
        markers = self._clickable_markers()
        if source is None or map_size <= 0 or not markers:
            self.map_status.configure(
                text="No live server-marker data is loaded for this map yet. Refresh the live server snapshot and map."
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
                text="No clickable server icon was found there. Click closer to the center of the icon."
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


if not getattr(_shop_value, "_strategic_reference_hotfix_installed", False):
    _shop_value.score_shop_rows = score_shop_rows_with_strategic_references
    _shop_value._strategic_reference_hotfix_installed = True

if not getattr(_map_enhanced, "_marker_click_hotfix_installed", False):
    _map_enhanced.MapTab = ClickableServerMarkerMapTab
    _map_enhanced._marker_click_hotfix_installed = True
