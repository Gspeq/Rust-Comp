from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw


RUST_GRID_METERS = 146.3
SHOP_GRID_MAP_SIZE = (310, 310)
SHOP_GRID_SPAN = 2


@dataclass(frozen=True, slots=True)
class ShopGridViewport:
    crop_box: tuple[int, int, int, int]
    marker_fraction: tuple[float, float]
    divider_fraction: tuple[float, float]
    grid_count: int
    span: int


def world_fraction(
    x: Any,
    y: Any,
    map_size: Any,
) -> tuple[float, float] | None:
    try:
        numeric_x = float(x)
        numeric_y = float(y)
        numeric_size = float(map_size)
    except (TypeError, ValueError):
        return None
    if numeric_size <= 0:
        return None
    if numeric_x < 0 or numeric_y < 0:
        half = numeric_size / 2.0
        x_fraction = (numeric_x + half) / numeric_size
        world_y_fraction = (numeric_y + half) / numeric_size
    else:
        x_fraction = numeric_x / numeric_size
        world_y_fraction = numeric_y / numeric_size
    return (
        min(1.0, max(0.0, x_fraction)),
        1.0 - min(1.0, max(0.0, world_y_fraction)),
    )


def shop_grid_viewport(
    image_size: tuple[int, int],
    x: Any,
    y: Any,
    map_size: Any,
    *,
    span: int = SHOP_GRID_SPAN,
) -> ShopGridViewport:
    """Return an aligned multi-cell crop and the shop's true position inside it."""
    width, height = image_size
    fractions = world_fraction(x, y, map_size) or (0.5, 0.5)
    try:
        numeric_size = max(1.0, float(map_size))
    except (TypeError, ValueError):
        numeric_size = 4000.0

    grid_count = max(1, math.ceil(numeric_size / RUST_GRID_METERS))
    effective_span = max(1, min(int(span), grid_count))
    cell_width = width / grid_count
    cell_height = height / grid_count

    raw_column = min(grid_count - 1, max(0, int(fractions[0] * grid_count)))
    raw_row = min(grid_count - 1, max(0, int(fractions[1] * grid_count)))
    local_x = fractions[0] * grid_count - raw_column
    local_y = fractions[1] * grid_count - raw_row

    if effective_span == 1:
        start_column = raw_column
        start_row = raw_row
    else:
        start_column = raw_column - (1 if local_x < 0.5 else 0)
        start_row = raw_row - (1 if local_y < 0.5 else 0)
        start_column = min(max(0, start_column), grid_count - effective_span)
        start_row = min(max(0, start_row), grid_count - effective_span)

    left = int(round(start_column * cell_width))
    top = int(round(start_row * cell_height))
    right = int(round((start_column + effective_span) * cell_width))
    bottom = int(round((start_row + effective_span) * cell_height))
    right = min(width, max(left + 1, right))
    bottom = min(height, max(top + 1, bottom))

    crop_width = max(1, right - left)
    crop_height = max(1, bottom - top)
    marker_x = min(1.0, max(0.0, (fractions[0] * width - left) / crop_width))
    marker_y = min(1.0, max(0.0, (fractions[1] * height - top) / crop_height))

    divider_x = (
        ((start_column + 1) * cell_width - left) / crop_width
        if effective_span >= 2
        else 0.5
    )
    divider_y = (
        ((start_row + 1) * cell_height - top) / crop_height
        if effective_span >= 2
        else 0.5
    )

    return ShopGridViewport(
        crop_box=(left, top, right, bottom),
        marker_fraction=(marker_x, marker_y),
        divider_fraction=(
            min(1.0, max(0.0, divider_x)),
            min(1.0, max(0.0, divider_y)),
        ),
        grid_count=grid_count,
        span=effective_span,
    )


def shop_grid_crop_box(
    image_size: tuple[int, int],
    x: Any,
    y: Any,
    map_size: Any,
) -> tuple[int, int, int, int]:
    return shop_grid_viewport(
        image_size,
        x,
        y,
        map_size,
    ).crop_box


def render_selected_shop_grid(
    base_image: Any,
    selected: Any,
    map_size: int,
    *,
    output_size: tuple[int, int] = SHOP_GRID_MAP_SIZE,
) -> Image.Image:
    """Render the selected shop inside an aligned 2×2 grid neighborhood."""
    width = max(120, int(output_size[0]))
    height = max(120, int(output_size[1]))
    size = (width, height)

    viewport: ShopGridViewport | None = None
    if isinstance(base_image, Image.Image):
        source = base_image.convert("RGBA")
        viewport = shop_grid_viewport(
            source.size,
            getattr(selected, "x", 0),
            getattr(selected, "y", 0),
            map_size,
        )
        crop = source.crop(viewport.crop_box)
        base = crop.resize(size, Image.Resampling.LANCZOS)
    else:
        base = Image.new("RGBA", size, (9, 15, 28, 255))
        viewport = ShopGridViewport(
            crop_box=(0, 0, width, height),
            marker_fraction=(0.5, 0.5),
            divider_fraction=(0.5, 0.5),
            grid_count=1,
            span=2,
        )

    draw = ImageDraw.Draw(base, "RGBA")
    draw.rectangle(
        (1, 1, width - 2, height - 2),
        outline=(226, 232, 240, 210),
        width=2,
    )

    divider_x = int(round(viewport.divider_fraction[0] * width))
    divider_y = int(round(viewport.divider_fraction[1] * height))
    if viewport.span >= 2:
        draw.line(
            (divider_x, 0, divider_x, height),
            fill=(226, 232, 240, 150),
            width=2,
        )
        draw.line(
            (0, divider_y, width, divider_y),
            fill=(226, 232, 240, 150),
            width=2,
        )

    center_x = int(round(viewport.marker_fraction[0] * width))
    center_y = int(round(viewport.marker_fraction[1] * height))
    center_x = min(width - 18, max(18, center_x))
    center_y = min(height - 18, max(18, center_y))
    radius = 13
    draw.ellipse(
        (
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
        ),
        fill=(245, 158, 11, 248),
        outline=(255, 255, 255, 255),
        width=3,
    )
    draw.line(
        (center_x - 19, center_y, center_x + 19, center_y),
        fill=(255, 255, 255, 245),
        width=2,
    )
    draw.line(
        (center_x, center_y - 19, center_x, center_y + 19),
        fill=(255, 255, 255, 245),
        width=2,
    )

    grid = str(getattr(selected, "grid", "?") or "?")
    shop = str(getattr(selected, "shop", "Selected shop") or "Selected shop")
    badge_width = min(width - 16, 246)
    draw.rounded_rectangle(
        (8, 8, 8 + badge_width, 56),
        radius=8,
        fill=(15, 23, 42, 230),
        outline=(148, 163, 184, 160),
        width=1,
    )
    draw.text(
        (16, 14),
        f"2×2 area around {grid}",
        fill=(251, 191, 36, 255),
    )
    draw.text(
        (16, 34),
        shop[:34],
        fill=(248, 250, 252, 255),
    )
    return base
