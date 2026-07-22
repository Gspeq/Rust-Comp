from __future__ import annotations

import math
from typing import Any

from PIL import Image, ImageDraw, ImageOps


RUST_GRID_METERS = 146.3
SHOP_GRID_MAP_SIZE = (310, 310)


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


def shop_grid_crop_box(
    image_size: tuple[int, int],
    x: Any,
    y: Any,
    map_size: Any,
) -> tuple[int, int, int, int]:
    width, height = image_size
    fractions = world_fraction(x, y, map_size) or (0.5, 0.5)
    try:
        numeric_size = max(1.0, float(map_size))
    except (TypeError, ValueError):
        numeric_size = 4000.0
    grid_count = max(1, math.ceil(numeric_size / RUST_GRID_METERS))
    crop_width = max(48, int(round(width / grid_count)))
    crop_height = max(48, int(round(height / grid_count)))
    center_x = fractions[0] * width
    center_y = fractions[1] * height
    left = int(round(center_x - crop_width / 2))
    top = int(round(center_y - crop_height / 2))
    left = min(max(0, left), max(0, width - crop_width))
    top = min(max(0, top), max(0, height - crop_height))
    return (
        left,
        top,
        min(width, left + crop_width),
        min(height, top + crop_height),
    )


def render_selected_shop_grid(
    base_image: Any,
    selected: Any,
    map_size: int,
    *,
    output_size: tuple[int, int] = SHOP_GRID_MAP_SIZE,
) -> Image.Image:
    """Render only the selected shop's fixed grid cell with one marker."""
    width = max(120, int(output_size[0]))
    height = max(120, int(output_size[1]))
    size = (width, height)

    if isinstance(base_image, Image.Image):
        source = base_image.convert("RGBA")
        crop = source.crop(
            shop_grid_crop_box(
                source.size,
                getattr(selected, "x", 0),
                getattr(selected, "y", 0),
                map_size,
            )
        )
        base = ImageOps.fit(
            crop,
            size,
            method=Image.Resampling.LANCZOS,
        )
    else:
        base = Image.new("RGBA", size, (9, 15, 28, 255))

    draw = ImageDraw.Draw(base, "RGBA")
    # One cell only: edge lines make the fixed grid crop explicit. No server,
    # event, team, vending, or matching-shop icons are added.
    draw.rectangle(
        (1, 1, width - 2, height - 2),
        outline=(226, 232, 240, 210),
        width=2,
    )
    center_x = width // 2
    center_y = height // 2
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
        (8, 8, 8 + badge_width, 52),
        radius=8,
        fill=(15, 23, 42, 230),
        outline=(148, 163, 184, 160),
        width=1,
    )
    draw.text(
        (16, 14),
        f"Grid {grid}",
        fill=(251, 191, 36, 255),
    )
    draw.text(
        (16, 31),
        shop[:34],
        fill=(248, 250, 252, 255),
    )
    return base
