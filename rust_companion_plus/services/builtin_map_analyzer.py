
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageFilter, ImageOps


ANALYSIS_SIZE = 640


@dataclass(frozen=True, slots=True)
class BuiltinMapAnalysis:
    output_dir: Path
    base_map_path: Path
    manifest_path: Path
    layers: dict[str, Path]
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


def _mask_from_bytes(size: tuple[int, int], values: Iterable[int]) -> Image.Image:
    return Image.frombytes(
        "L",
        size,
        bytes(max(0, min(255, int(value))) for value in values),
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


def _soften(mask: Image.Image, radius: float = 5.0) -> Image.Image:
    return mask.filter(ImageFilter.GaussianBlur(radius))


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
    safe = "_".join(part for part in safe.split() if part)
    path = output_dir / f"heatmap_{safe}.png"
    mask.convert("L").save(path, format="PNG", optimize=True)
    return path


def analyze_map_image(
    image: Image.Image,
    output_dir: str | Path,
    *,
    world_size: int = 0,
    markers: Iterable[dict[str, Any]] | None = None,
) -> BuiltinMapAnalysis:
    """Create built-in terrain and habitat heatmaps from a Rust+ map image.

    Rust ore nodes and animals are dynamic server entities. The generated
    ore and animal layers are therefore suitability/likelihood layers based
    on visible biome, terrain roughness, coastline, and road evidence. They
    deliberately do not claim exact live spawn coordinates.
    """
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    full = image.convert("RGBA")
    base_path = output / "current_map_texture.png"
    full.save(base_path, format="PNG", optimize=True)

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
        lambda h, s, v: 118 <= h <= 190 and s >= 40 and v >= 28,
        hue,
        saturation,
        value,
    )
    snow = _binary(
        size,
        lambda h, s, v: s <= 48 and v >= 150 and not (118 <= h <= 190 and s >= 40),
        hue,
        saturation,
        value,
    )
    desert = _binary(
        size,
        lambda h, s, v: 10 <= h <= 52 and s >= 28 and v >= 70,
        hue,
        saturation,
        value,
    )
    temperate = _binary(
        size,
        lambda h, s, v: 42 <= h <= 112 and s >= 25 and v >= 38,
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
        grayscale.filter(ImageFilter.FIND_EDGES)
    ).filter(ImageFilter.GaussianBlur(1.2))
    rough = terrain_edges.point(
        lambda item: max(0, min(255, int((item - 18) * 2.2)))
    )
    rough = _intersect(rough, land)

    expanded_water = water.filter(ImageFilter.MaxFilter(17))
    coastline = ImageChops.subtract(expanded_water, water)
    coastline = _intersect(coastline, land)

    low_saturation = _binary(
        size,
        lambda s, v: s <= 54 and 58 <= v <= 210,
        saturation,
        value,
    )
    road_access = _intersect(low_saturation, land)
    road_access = ImageChops.subtract(road_access, rough.point(lambda v: min(255, v * 2)))
    road_access = _soften(road_access.filter(ImageFilter.MaxFilter(3)), 1.5)

    open_land = ImageChops.subtract(
        _union(temperate, desert),
        rough.point(lambda item: min(255, item * 2)),
    )
    forest = _binary(
        size,
        lambda h, s, v: 45 <= h <= 105 and s >= 48 and 35 <= v <= 155,
        hue,
        saturation,
        value,
    )
    forest = _intersect(forest, land)

    stone = _soften(_intersect(rough, _union(temperate, desert, snow)), 5)
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
            _intersect(rough, temperate).point(lambda item: int(item * 0.55)),
        ),
        6,
    )
    junk = _soften(road_access, 7)

    bear = _soften(_union(forest, _intersect(temperate, rough)), 10)
    wolf = _soften(_union(forest, _intersect(snow, rough)), 10)
    boar = _soften(_intersect(temperate, ImageChops.invert(rough)), 12)
    horse = _soften(open_land, 12)
    chicken = _soften(
        _intersect(temperate, ImageChops.invert(rough)),
        14,
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
        "Water": water,
        "Coastline": coastline,
        "Road Access": road_access,
        "Snow Biome": snow,
        "Desert Biome": desert,
        "Temperate Biome": temperate,
        "Rough Terrain": rough,
    }

    layer_paths = {
        name: _save_layer(output, name, mask)
        for name, mask in masks.items()
    }

    marker_rows = [
        {
            "id": str(marker.get("id") or ""),
            "type": int(marker.get("type", 0) or 0),
            "x": float(marker.get("x", 0) or 0),
            "y": float(marker.get("y", 0) or 0),
            "name": str(marker.get("name") or ""),
        }
        for marker in (markers or [])
        if isinstance(marker, dict)
    ]

    manifest = {
        "format": "rust-companion-plus-builtin-map-analysis-v1",
        "world_size": int(world_size or 0),
        "analysis_size": list(size),
        "base_map": base_path.name,
        "layers": {
            name: path.name
            for name, path in layer_paths.items()
        },
        "markers": marker_rows,
        "accuracy": {
            "static_layers": (
                "Biome, water, coastline, rough-terrain, and road-access "
                "layers are derived from visible map pixels."
            ),
            "dynamic_layers": (
                "Ore and animal layers are suitability estimates. Rust "
                "spawns these entities dynamically, so exact live spawn "
                "coordinates are not available from the map image."
            ),
        },
    }
    manifest_path = output / "map_resolved.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )

    return BuiltinMapAnalysis(
        output_dir=output,
        base_map_path=base_path,
        manifest_path=manifest_path,
        layers=layer_paths,
        world_size=int(world_size or 0),
    )
