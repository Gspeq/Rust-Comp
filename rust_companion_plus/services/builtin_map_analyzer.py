from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


ANALYSIS_SIZE = 640


@dataclass(frozen=True, slots=True)
class BuiltinMapAnalysis:
    output_dir: Path
    base_map_path: Path
    manifest_path: Path
    layers: dict[str, Path]
    monuments: list[dict[str, Any]]
    world_size: int


def _fit_for_analysis(image: Image.Image) -> Image.Image:
    source = image.convert("RGBA")
    width, height = source.size
    if max(width, height) <= ANALYSIS_SIZE:
        return source.copy()
    scale = ANALYSIS_SIZE / max(width, height)
    return source.resize(
        (
            max(64, int(round(width * scale))),
            max(64, int(round(height * scale))),
        ),
        Image.Resampling.LANCZOS,
    )


def _mask_from_bytes(
    size: tuple[int, int],
    values: Iterable[int],
) -> Image.Image:
    return Image.frombytes(
        "L",
        size,
        bytes(
            max(0, min(255, int(value)))
            for value in values
        ),
    )


def _binary(
    size: tuple[int, int],
    predicate,
    *channels: list[int],
) -> Image.Image:
    return _mask_from_bytes(
        size,
        (
            255 if predicate(*values) else 0
            for values in zip(*channels)
        ),
    )


def _intersect(*masks: Image.Image) -> Image.Image:
    result = masks[0]
    for mask in masks[1:]:
        result = ImageChops.multiply(result, mask)
    return result


def _union(*masks: Image.Image) -> Image.Image:
    result = masks[0]
    for mask in masks[1:]:
        result = ImageChops.lighter(result, mask)
    return result


def _soften(
    mask: Image.Image,
    radius: float = 5.0,
) -> Image.Image:
    return mask.filter(
        ImageFilter.GaussianBlur(radius)
    )


def _save_layer(
    output_dir: Path,
    label: str,
    mask: Image.Image,
) -> Path:
    safe = (
        label.casefold()
        .replace("/", " ")
        .replace("&", " and ")
    )
    safe = "_".join(
        part for part in safe.split() if part
    )
    path = output_dir / f"heatmap_{safe}.png"
    mask.convert("L").save(
        path,
        format="PNG",
        optimize=True,
    )
    return path


def _world_fraction(
    x: float,
    y: float,
    world_size: int,
) -> tuple[float, float] | None:
    if world_size <= 0:
        return None
    half = world_size / 2.0
    if (
        -half - 100 <= x <= half + 100
        and -half - 100 <= y <= half + 100
    ):
        fx = (x + half) / world_size
        fy = (y + half) / world_size
    elif (
        -100 <= x <= world_size + 100
        and -100 <= y <= world_size + 100
    ):
        fx = x / world_size
        fy = y / world_size
    else:
        return None
    return (
        min(1.0, max(0.0, fx)),
        min(1.0, max(0.0, fy)),
    )


def _connected_components(
    mask: Image.Image,
) -> list[dict[str, float]]:
    binary = mask.convert("L")
    width, height = binary.size
    data = binary.tobytes()
    seen = bytearray(width * height)
    rows: list[dict[str, float]] = []

    for start, value in enumerate(data):
        if value < 128 or seen[start]:
            continue

        queue: deque[int] = deque([start])
        seen[start] = 1
        count = 0
        min_x = max_x = start % width
        min_y = max_y = start // width

        while queue:
            position = queue.popleft()
            x = position % width
            y = position // width
            count += 1
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

            for candidate in (
                position - 1,
                position + 1,
                position - width,
                position + width,
            ):
                if (
                    candidate < 0
                    or candidate >= width * height
                    or seen[candidate]
                    or data[candidate] < 128
                ):
                    continue
                cx = candidate % width
                cy = candidate // width
                if abs(cx - x) + abs(cy - y) != 1:
                    continue
                seen[candidate] = 1
                queue.append(candidate)

        box_width = max_x - min_x + 1
        box_height = max_y - min_y + 1
        area = box_width * box_height
        if area <= 0:
            continue
        fill = count / area
        aspect = box_width / max(1, box_height)

        if not (
            22 <= count <= 3200
            and 7 <= box_width <= 70
            and 7 <= box_height <= 70
            and 0.50 <= aspect <= 2.0
            and fill >= 0.10
        ):
            continue

        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        if (
            center_x <= width * 0.015
            or center_x >= width * 0.985
            or center_y <= height * 0.015
            or center_y >= height * 0.985
        ):
            continue

        rows.append(
            {
                "center_x": center_x,
                "center_y": center_y,
                "width": float(box_width),
                "height": float(box_height),
                "pixels": float(count),
                "fill": fill,
            }
        )
    return rows


def _dynamic_marker_fractions(
    markers: Iterable[dict[str, Any]] | None,
    world_size: int,
) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    for marker in markers or []:
        if not isinstance(marker, dict):
            continue
        try:
            x = float(marker.get("x", 0) or 0)
            y = float(marker.get("y", 0) or 0)
        except (TypeError, ValueError):
            continue
        normalized = _world_fraction(
            x,
            y,
            world_size,
        )
        if normalized is not None:
            rows.append(normalized)
    return rows


def detect_monument_markers(
    image: Image.Image,
    *,
    world_size: int = 0,
    dynamic_markers: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Detect large red/blue Rust+ map icons.

    Rust+ does not provide monument names or coordinates directly through the
    team feed. This detector therefore reports approximate visible monument
    marker centers and excludes locations that overlap known live markers.
    """
    source = _fit_for_analysis(image)
    hsv = source.convert("RGB").convert("HSV")
    hue_image, saturation_image, value_image = hsv.split()
    hue = list(hue_image.getdata())
    saturation = list(saturation_image.getdata())
    value = list(value_image.getdata())
    size = source.size

    color_masks = {
        "red": _binary(
            size,
            lambda h, s, v: (
                (h <= 18 or h >= 238)
                and s >= 120
                and v >= 125
            ),
            hue,
            saturation,
            value,
        ),
        "blue": _binary(
            size,
            lambda h, s, v: (
                125 <= h <= 188
                and s >= 105
                and v >= 105
            ),
            hue,
            saturation,
            value,
        ),
    }

    dynamic = _dynamic_marker_fractions(
        dynamic_markers,
        world_size,
    )
    exclusion_radius = (
        max(0.022, 105.0 / world_size)
        if world_size > 0
        else 0.03
    )

    detected: list[dict[str, Any]] = []
    width, height = size

    for color, raw_mask in color_masks.items():
        mask = raw_mask.filter(
            ImageFilter.MaxFilter(3)
        ).filter(
            ImageFilter.MinFilter(3)
        )

        for component in _connected_components(mask):
            fx = component["center_x"] / max(1, width - 1)
            # Rust world north is upward; image Y increases downward.
            fy = 1.0 - (
                component["center_y"] / max(1, height - 1)
            )

            if any(
                math.hypot(fx - mx, fy - my)
                <= exclusion_radius
                for mx, my in dynamic
            ):
                continue

            if any(
                math.hypot(
                    fx - float(item["x_fraction"]),
                    fy - float(item["y_fraction"]),
                )
                <= 0.018
                for item in detected
            ):
                continue

            confidence = min(
                0.99,
                max(
                    0.45,
                    0.45
                    + component["fill"] * 0.4
                    + min(
                        component["width"],
                        component["height"],
                    )
                    / 180.0,
                ),
            )
            detected.append(
                {
                    "x_fraction": round(fx, 6),
                    "y_fraction": round(fy, 6),
                    "color": color,
                    "confidence": round(confidence, 3),
                }
            )

    detected.sort(
        key=lambda row: (
            -float(row["y_fraction"]),
            float(row["x_fraction"]),
        )
    )
    for index, row in enumerate(detected, start=1):
        row["label"] = f"Monument marker {index}"
    return detected[:80]


def _monument_proximity_mask(
    size: tuple[int, int],
    monuments: list[dict[str, Any]],
) -> Image.Image:
    mask = Image.new("L", size, 0)
    if not monuments:
        return mask
    width, height = size
    draw = ImageDraw.Draw(mask)
    radius = max(8, int(round(min(size) * 0.026)))
    for marker in monuments:
        x = int(
            float(marker["x_fraction"])
            * max(1, width - 1)
        )
        y = int(
            (1.0 - float(marker["y_fraction"]))
            * max(1, height - 1)
        )
        draw.ellipse(
            (
                x - radius,
                y - radius,
                x + radius,
                y + radius,
            ),
            fill=225,
        )
    return mask.filter(
        ImageFilter.GaussianBlur(
            max(4, radius * 0.75)
        )
    )


def analyze_map_image(
    image: Image.Image,
    output_dir: str | Path,
    *,
    world_size: int = 0,
    markers: Iterable[dict[str, Any]] | None = None,
) -> BuiltinMapAnalysis:
    """Create static and predictive layers from a Rust+ map image.

    Biome, terrain, water, road, and visible icon layers come from map pixels.
    Ore and animal layers are suitability estimates because exact live entity
    spawn coordinates are not exposed by the Rust+ map image.
    """
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    full = image.convert("RGBA")
    base_path = output / "current_map_texture.png"
    full.save(
        base_path,
        format="PNG",
        optimize=True,
    )

    analysis = _fit_for_analysis(full)
    rgb = analysis.convert("RGB")
    hsv = rgb.convert("HSV")
    hue_image, saturation_image, value_image = hsv.split()
    hue = list(hue_image.getdata())
    saturation = list(saturation_image.getdata())
    value = list(value_image.getdata())
    size = analysis.size

    water = _binary(
        size,
        lambda h, s, v: (
            118 <= h <= 190
            and s >= 40
            and v >= 28
        ),
        hue,
        saturation,
        value,
    )
    snow = _binary(
        size,
        lambda h, s, v: (
            s <= 48
            and v >= 150
            and not (
                118 <= h <= 190
                and s >= 40
            )
        ),
        hue,
        saturation,
        value,
    )
    desert = _binary(
        size,
        lambda h, s, v: (
            10 <= h <= 52
            and s >= 28
            and v >= 70
        ),
        hue,
        saturation,
        value,
    )
    temperate = _binary(
        size,
        lambda h, s, v: (
            42 <= h <= 112
            and s >= 25
            and v >= 38
        ),
        hue,
        saturation,
        value,
    )
    land = ImageChops.invert(water)
    snow = _intersect(snow, land)
    desert = _intersect(desert, land)
    temperate = _intersect(temperate, land)

    grayscale = ImageOps.grayscale(rgb)
    terrain_edges = ImageOps.autocontrast(
        grayscale.filter(
            ImageFilter.FIND_EDGES
        )
    ).filter(
        ImageFilter.GaussianBlur(1.2)
    )
    rough = terrain_edges.point(
        lambda item: max(
            0,
            min(255, int((item - 18) * 2.2)),
        )
    )
    rough = _intersect(rough, land)

    expanded_water = water.filter(
        ImageFilter.MaxFilter(17)
    )
    coastline = ImageChops.subtract(
        expanded_water,
        water,
    )
    coastline = _intersect(coastline, land)

    low_saturation = _binary(
        size,
        lambda s, v: (
            s <= 54
            and 58 <= v <= 210
        ),
        saturation,
        value,
    )
    road_access = _intersect(
        low_saturation,
        land,
    )
    road_access = ImageChops.subtract(
        road_access,
        rough.point(
            lambda item: min(255, item * 2)
        ),
    )
    road_access = _soften(
        road_access.filter(
            ImageFilter.MaxFilter(3)
        ),
        1.5,
    )

    open_land = ImageChops.subtract(
        _union(temperate, desert),
        rough.point(
            lambda item: min(255, item * 2)
        ),
    )
    forest = _binary(
        size,
        lambda h, s, v: (
            45 <= h <= 105
            and s >= 48
            and 35 <= v <= 155
        ),
        hue,
        saturation,
        value,
    )
    forest = _intersect(forest, land)

    stone = _soften(
        _intersect(
            rough,
            _union(temperate, desert, snow),
        ),
        5,
    )
    metal = _soften(
        _union(
            _intersect(rough, temperate),
            _intersect(rough, snow),
        ),
        6,
    )
    sulfur = _soften(
        _union(
            _intersect(rough, desert),
            _intersect(
                rough,
                temperate,
            ).point(
                lambda item: int(item * 0.55)
            ),
        ),
        6,
    )
    junk = _soften(road_access, 7)

    bear = _soften(
        _union(
            forest,
            _intersect(temperate, rough),
        ),
        10,
    )
    wolf = _soften(
        _union(
            forest,
            _intersect(snow, rough),
        ),
        10,
    )
    boar = _soften(
        _intersect(
            temperate,
            ImageChops.invert(rough),
        ),
        12,
    )
    horse = _soften(open_land, 12)
    chicken = _soften(
        _intersect(
            temperate,
            ImageChops.invert(rough),
        ),
        14,
    )

    monuments = detect_monument_markers(
        full,
        world_size=world_size,
        dynamic_markers=markers,
    )
    monument_proximity = _monument_proximity_mask(
        size,
        monuments,
    )

    masks = {
        "Stone": stone,
        "Metal": metal,
        "Sulfur": sulfur,
        "Junk Piles": junk,
        "Bear": bear,
        "Boar": boar,
        "Horse": horse,
        "Wolf": wolf,
        "Chicken": chicken,
        "Monument Proximity": monument_proximity,
        "Water": water,
        "Coastline": coastline,
        "Road Access": road_access,
        "Snow Biome": snow,
        "Desert Biome": desert,
        "Temperate Biome": temperate,
        "Rough Terrain": rough,
    }

    layer_paths = {
        name: _save_layer(
            output,
            name,
            mask,
        )
        for name, mask in masks.items()
    }

    marker_rows = [
        {
            "id": str(marker.get("id") or ""),
            "type": int(
                marker.get("type", 0) or 0
            ),
            "x": float(
                marker.get("x", 0) or 0
            ),
            "y": float(
                marker.get("y", 0) or 0
            ),
            "name": str(
                marker.get("name") or ""
            ),
        }
        for marker in (markers or [])
        if isinstance(marker, dict)
    ]

    manifest = {
        "format": (
            "rust-companion-plus-builtin-map-analysis-v2"
        ),
        "world_size": int(world_size or 0),
        "analysis_size": list(size),
        "base_map": base_path.name,
        "layers": {
            name: path.name
            for name, path in layer_paths.items()
        },
        "monuments": monuments,
        "markers": marker_rows,
        "accuracy": {
            "static_layers": (
                "Biome, water, coastline, rough-terrain, road-access, "
                "and visible monument-marker layers are derived from "
                "the current Rust+ map image."
            ),
            "predictive_layers": (
                "Ore and animal layers are likelihood or habitat "
                "estimates. Rust spawns those entities dynamically, "
                "so exact live spawn coordinates are not claimed."
            ),
            "monument_detection": (
                "Monument proximity uses large red/blue visible map "
                "icons after excluding known live Rust+ markers. The "
                "marker center is approximate and the monument name "
                "is not available through the Rust+ team feed."
            ),
        },
    }
    manifest_path = output / "map_resolved.json"
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
        newline="\n",
    )

    return BuiltinMapAnalysis(
        output_dir=output,
        base_map_path=base_path,
        manifest_path=manifest_path,
        layers=layer_paths,
        monuments=monuments,
        world_size=int(world_size or 0),
    )
