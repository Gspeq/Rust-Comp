from __future__ import annotations

import csv
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from rust_companion_plus.config import APP_DATA_DIR



RESOURCE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "Stone": {
        "color": (186, 186, 186),
        "aliases": (
            "stone ore",
            "stone_ore",
            "ore_stone",
            "stone-ore",
            "stone node",
        ),
        "kind": "likelihood",
    },
    "Metal": {
        "color": (66, 153, 225),
        "aliases": (
            "metal ore",
            "metal_ore",
            "ore_metal",
            "metal-ore",
            "metal node",
        ),
        "kind": "likelihood",
    },
    "Sulfur": {
        "color": (250, 204, 21),
        "aliases": (
            "sulfur ore",
            "sulfur_ore",
            "ore_sulfur",
            "sulfur-ore",
            "sulphur",
            "sulfur node",
        ),
        "kind": "likelihood",
    },
    "Junk Piles": {
        "color": (249, 115, 22),
        "aliases": (
            "junkpile",
            "junk pile",
            "junk_pile",
            "roadside junk",
            "trash pile",
        ),
        "kind": "likelihood",
    },
    "Bear": {
        "color": (124, 83, 54),
        "aliases": (
            "bear.prefab",
            "/bear/",
            " bear ",
        ),
        "kind": "habitat",
    },
    "Boar": {
        "color": (168, 85, 247),
        "aliases": (
            "boar.prefab",
            "/boar/",
            " boar ",
        ),
        "kind": "habitat",
    },
    "Horse": {
        "color": (34, 197, 94),
        "aliases": (
            "horse.prefab",
            "/horse/",
            " horse ",
        ),
        "kind": "habitat",
    },
    "Wolf": {
        "color": (148, 163, 184),
        "aliases": (
            "wolf.prefab",
            "/wolf/",
            " wolf ",
        ),
        "kind": "habitat",
    },
    "Chicken": {
        "color": (244, 114, 182),
        "aliases": (
            "chicken.prefab",
            "/chicken/",
            " chicken ",
        ),
        "kind": "habitat",
    },
    "Monument Proximity": {
        "color": (56, 189, 248),
        "aliases": (
            "monument proximity",
            "monument marker",
            "monument",
        ),
        "kind": "static",
    },
    "Water": {
        "color": (14, 165, 233),
        "aliases": ("water mask", "water"),
        "kind": "static",
    },
    "Coastline": {
        "color": (6, 182, 212),
        "aliases": ("coastline", "coast"),
        "kind": "static",
    },
    "Road Access": {
        "color": (251, 146, 60),
        "aliases": (
            "road access",
            "road density",
            "roads",
        ),
        "kind": "static",
    },
    "Snow Biome": {
        "color": (226, 232, 240),
        "aliases": (
            "snow biome",
            "snow mask",
            "snow",
        ),
        "kind": "static",
    },
    "Desert Biome": {
        "color": (245, 158, 11),
        "aliases": (
            "desert biome",
            "desert mask",
            "desert",
        ),
        "kind": "static",
    },
    "Temperate Biome": {
        "color": (74, 222, 128),
        "aliases": (
            "temperate biome",
            "temperate mask",
            "temperate",
        ),
        "kind": "static",
    },
    "Rough Terrain": {
        "color": (203, 213, 225),
        "aliases": (
            "rough terrain",
            "terrain roughness",
            "roughness",
        ),
        "kind": "static",
    },
}




@dataclass(slots=True)
class HeatPoint:
    resource: str
    x_fraction: float
    y_fraction: float
    weight: float = 1.0
    source: str = ""


@dataclass(slots=True)
class ResourceHeatmapBundle:
    source_root: Path
    points: dict[str, list[HeatPoint]] = field(default_factory=dict)
    raster_layers: dict[str, list[Path]] = field(default_factory=dict)
    detected_world_size: int = 0
    files_scanned: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def resources(self) -> list[str]:
        return sorted(set(self.points) | set(self.raster_layers))

    def count_for(self, resource: str) -> int:
        return len(self.points.get(resource, [])) + len(self.raster_layers.get(resource, []))


@dataclass(slots=True)
class Hotspot:
    resource_label: str
    x_fraction: float
    y_fraction: float
    intensity: int


def classify_resource(text: str) -> str | None:
    normalized = f" {text.lower().replace('\\\\', '/').replace('_', ' ')} "
    for resource, definition in RESOURCE_DEFINITIONS.items():
        for alias in definition["aliases"]:
            candidate = alias.lower().replace("_", " ")
            if candidate in normalized:
                return resource
    return None


def _first_number(mapping: dict[str, Any], keys: Iterable[str]) -> float | None:
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    return None


def _all_strings(mapping: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in mapping.items():
        if isinstance(value, str):
            parts.append(f"{key} {value}")
    return " ".join(parts)


def _walk_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_objects(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_objects(nested)


def _detect_world_size_from_json(value: Any) -> int:
    candidates: list[float] = []
    for obj in _walk_objects(value):
        number = _first_number(obj, ("world_size", "worldsize", "map_size", "mapsize", "size"))
        if number and 1000 <= number <= 10000:
            candidates.append(number)
    return int(round(max(candidates))) if candidates else 0


def _normalize_xy(x: float, y: float, world_size: int) -> tuple[float, float] | None:
    if -0.001 <= x <= 1.001 and -0.001 <= y <= 1.001:
        return min(1.0, max(0.0, x)), min(1.0, max(0.0, y))
    if world_size <= 0:
        return None

    half = world_size / 2.0
    if -half - 100 <= x <= half + 100 and -half - 100 <= y <= half + 100:
        nx = (x + half) / world_size
        ny = (y + half) / world_size
    elif -100 <= x <= world_size + 100 and -100 <= y <= world_size + 100:
        nx = x / world_size
        ny = y / world_size
    else:
        return None

    if -0.05 <= nx <= 1.05 and -0.05 <= ny <= 1.05:
        return min(1.0, max(0.0, nx)), min(1.0, max(0.0, ny))
    return None


def extract_points_from_json(path: Path, world_size: int = 0) -> tuple[list[HeatPoint], int, list[str]]:
    warnings: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], 0, [f"Could not read {path.name}: {exc}"]

    detected_size = _detect_world_size_from_json(payload)
    effective_size = world_size or detected_size
    raw_matches: list[tuple[str, float, float, float]] = []

    for obj in _walk_objects(payload):
        resource = classify_resource(_all_strings(obj))
        if resource is None:
            continue
        x = _first_number(obj, ("x", "world_x", "position_x", "pos_x"))
        y = _first_number(obj, ("y", "z", "world_y", "world_z", "position_y", "position_z", "pos_y", "pos_z"))
        if x is None or y is None:
            position = obj.get("position") or obj.get("pos") or obj.get("Position")
            if isinstance(position, dict):
                x = _first_number(position, ("x",))
                y = _first_number(position, ("y", "z"))
        if x is None or y is None:
            continue
        weight = _first_number(obj, ("weight", "density", "intensity", "count")) or 1.0
        raw_matches.append((resource, x, y, max(0.01, weight)))

    if raw_matches and effective_size <= 0:
        values = [abs(number) for _resource, x, y, _weight in raw_matches for number in (x, y)]
        max_abs = max(values, default=0)
        # Rust procedural maps normally use familiar round sizes. This inference is
        # only a fallback when the parser output does not include metadata.
        for candidate in (1000, 2000, 2500, 3000, 3500, 4000, 4250, 4500, 5000, 5500, 6000):
            if max_abs <= candidate / 2 + 100:
                effective_size = candidate
                break
        if effective_size <= 0 and max_abs <= 6500:
            effective_size = int(math.ceil(max_abs * 2 / 250) * 250)

    points: list[HeatPoint] = []
    skipped = 0
    for resource, x, y, weight in raw_matches:
        normalized = _normalize_xy(x, y, effective_size)
        if normalized is None:
            skipped += 1
            continue
        nx, ny = normalized
        points.append(HeatPoint(resource, nx, ny, weight, path.name))

    if skipped:
        warnings.append(f"{path.name}: skipped {skipped} points with unknown coordinate scale.")
    return points, effective_size, warnings


def extract_points_from_csv(path: Path, world_size: int = 0) -> tuple[list[HeatPoint], list[str]]:
    warnings: list[str] = []
    points: list[HeatPoint] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                resource = classify_resource(" ".join(str(value) for value in row.values()))
                if resource is None:
                    continue
                x = _first_number(row, ("x", "world_x", "position_x", "pos_x"))
                y = _first_number(row, ("y", "z", "world_y", "world_z", "position_y", "position_z", "pos_y", "pos_z"))
                if x is None or y is None:
                    continue
                normalized = _normalize_xy(x, y, world_size)
                if normalized is None:
                    continue
                weight = _first_number(row, ("weight", "density", "intensity", "count")) or 1.0
                points.append(HeatPoint(resource, *normalized, max(0.01, weight), path.name))
    except (OSError, csv.Error) as exc:
        warnings.append(f"Could not read {path.name}: {exc}")
    return points, warnings


def _raster_resource(path: Path) -> str | None:
    lowered = str(path).lower().replace("_", " ").replace("-", " ")
    if not any(token in lowered for token in ("heatmap", "heat map", "density", "resource", "spawn", "mask")):
        return None
    for resource in RESOURCE_DEFINITIONS:
        singular = resource.lower().removesuffix(" piles")
        if re.search(rf"\b{re.escape(singular)}\b", lowered):
            return resource
    return classify_resource(lowered)


def load_heatmap_bundle(root: str | Path, world_size: int = 0) -> ResourceHeatmapBundle:
    root_path = Path(root).expanduser().resolve()
    bundle = ResourceHeatmapBundle(source_root=root_path)
    if not root_path.exists():
        bundle.warnings.append(f"Source does not exist: {root_path}")
        return bundle

    if root_path.is_file():
        files = [root_path]
    else:
        files = [path for path in root_path.rglob("*") if path.is_file()]

    json_files = [path for path in files if path.suffix.lower() in {".json", ".jsonl"}]
    preferred_json = [
        path for path in json_files
        if path.name.lower() in {"map_resolved.json", "map_data.json", "map_raw.json", "resources.json", "heatmaps.json"}
        or any(token in path.name.lower() for token in ("resource", "spawn", "heatmap"))
    ]
    if preferred_json:
        json_files = preferred_json

    effective_size = world_size
    for path in json_files:
        points, detected_size, warnings = extract_points_from_json(path, effective_size)
        if detected_size and not effective_size:
            effective_size = detected_size
        for point in points:
            bundle.points.setdefault(point.resource, []).append(point)
        bundle.warnings.extend(warnings)
        bundle.files_scanned += 1

    for path in files:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            points, warnings = extract_points_from_csv(path, effective_size)
            for point in points:
                bundle.points.setdefault(point.resource, []).append(point)
            bundle.warnings.extend(warnings)
            bundle.files_scanned += 1
        elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            resource = _raster_resource(path)
            if resource:
                bundle.raster_layers.setdefault(resource, []).append(path)
                bundle.files_scanned += 1

    # Deduplicate points that appear in map_raw, map_data and map_resolved together.
    for resource, points in list(bundle.points.items()):
        unique: dict[tuple[int, int], HeatPoint] = {}
        for point in points:
            key = (round(point.x_fraction * 10000), round(point.y_fraction * 10000))
            previous = unique.get(key)
            if previous is None or point.weight > previous.weight:
                unique[key] = point
        bundle.points[resource] = list(unique.values())

    bundle.detected_world_size = effective_size
    if not bundle.resources:
        bundle.warnings.append(
            "No recognized resource layers were found. Import a parser output folder containing "
            "map_resolved.json/map_data.json, a CSV/JSON point export, or named heatmap image masks."
        )
    return bundle


def default_cache_roots() -> list[Path]:
    roots: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.extend(
            [
                Path(appdata) / "RustPlusDesk" / "3DMaps",
                Path(appdata) / "RustPlusDesk" / "Map3DViewer" / "maps",
            ]
        )
    roots.append(APP_DATA_DIR / "heatmaps")
    return roots


def find_best_cache_folder(world_size: int = 0) -> Path | None:
    candidates: list[tuple[int, float, Path]] = []
    for root in default_cache_roots():
        if not root.exists():
            continue
        folders = [root] + [path for path in root.iterdir() if path.is_dir()]
        for folder in folders:
            score = 0
            for name in ("map_resolved.json", "map_data.json", "map_raw.json"):
                if (folder / name).exists():
                    score += 3
            heatmap_count = sum(1 for path in folder.rglob("*.png") if _raster_resource(path))
            score += min(20, heatmap_count)
            if score:
                try:
                    modified = max(path.stat().st_mtime for path in folder.rglob("*") if path.is_file())
                except (OSError, ValueError):
                    modified = folder.stat().st_mtime
                candidates.append((score, modified, folder))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return candidates[0][2]


def find_map_parser() -> Path | None:
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.extend(
            [
                Path(appdata) / "RustPlusDesk" / "cache" / "map3d-parser-runtime" / "MapParser.exe",
                Path(appdata) / "RustPlusDesk" / "MapParser.exe",
            ]
        )
    candidates.extend(
        [
            Path.cwd() / "MapParser.exe",
            Path.cwd() / "MapParser" / "MapParser.exe",
            APP_DATA_DIR / "MapParser.exe",
        ]
    )
    return next((path for path in candidates if path.is_file()), None)


def parse_local_map(
    map_path: str | Path,
    output_dir: str | Path,
    parser_path: str | Path | None = None,
    timeout_seconds: int = 300,
) -> Path:
    source = Path(map_path).expanduser().resolve()
    parser = Path(parser_path).expanduser().resolve() if parser_path else find_map_parser()
    output = Path(output_dir).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".map":
        raise ValueError("Choose a valid Rust .map file.")
    if parser is None or not parser.is_file():
        raise FileNotFoundError(
            "MapParser.exe was not found. Install RustPlusDesktop 7.1+ or place a compatible "
            "MapParser.exe beside this app. You can still import an already parsed cache folder."
        )
    output.mkdir(parents=True, exist_ok=True)
    command = [str(parser), str(source), "--output-dir", str(output)]
    completed = subprocess.run(
        command,
        cwd=str(parser.parent),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    (output / "parser_log.txt").write_text(
        f"Command: {command!r}\n\n--- STDOUT ---\n{completed.stdout}\n\n"
        f"--- STDERR ---\n{completed.stderr}\n\nExitCode: {completed.returncode}\n",
        encoding="utf-8",
    )
    resolved = output / "map_resolved.json"
    if completed.returncode != 0 or not resolved.exists():
        raise RuntimeError(
            f"Map parser failed with exit code {completed.returncode}. See {output / 'parser_log.txt'}"
        )
    return output


def _load_raster_mask(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    alpha = image.getchannel("A")
    gray = ImageOps.grayscale(image)
    if alpha.getextrema() != (255, 255):
        return ImageChops.lighter(gray, alpha)
    return gray


def build_resource_mask(
    bundle: ResourceHeatmapBundle,
    resource: str,
    size: tuple[int, int],
    point_radius: int = 18,
    blur_radius: int = 24,
) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 0)

    for path in bundle.raster_layers.get(resource, []):
        try:
            mask = ImageChops.lighter(mask, _load_raster_mask(path, size))
        except OSError:
            continue

    points = bundle.points.get(resource, [])
    if points:
        point_mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(point_mask)
        for point in points:
            x = int(point.x_fraction * (width - 1))
            # Rust world Y increases north; image Y increases downward.
            y = int((1.0 - point.y_fraction) * (height - 1))
            strength = max(35, min(255, int(100 * point.weight)))
            radius = max(2, point_radius)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=strength)
        if blur_radius > 0:
            point_mask = point_mask.filter(ImageFilter.GaussianBlur(blur_radius))
        mask = ImageChops.lighter(mask, point_mask)
    return mask


def colorize_mask(mask: Image.Image, resource: str, opacity: float = 0.65) -> Image.Image:
    color = RESOURCE_DEFINITIONS[resource]["color"]
    alpha = mask.point(lambda value: int(value * min(1.0, max(0.0, opacity))))
    layer = Image.new("RGBA", mask.size, (*color, 0))
    layer.putalpha(alpha)
    return layer


def composite_heatmaps(
    base_image: Image.Image,
    bundle: ResourceHeatmapBundle | None,
    selected_resources: Iterable[str],
    opacity: float = 0.65,
    point_radius: int = 18,
    blur_radius: int = 24,
) -> Image.Image:
    result = base_image.convert("RGBA")
    if bundle is None:
        return result
    for resource in selected_resources:
        if resource not in RESOURCE_DEFINITIONS:
            continue
        mask = build_resource_mask(bundle, resource, result.size, point_radius, blur_radius)
        if mask.getbbox() is None:
            continue
        result = Image.alpha_composite(result, colorize_mask(mask, resource, opacity))
    return result


def rank_hotspots(
    bundle: ResourceHeatmapBundle | None,
    resources: Iterable[str],
    limit: int = 8,
    resolution: int = 128,
    point_radius: int = 3,
    blur_radius: int = 5,
) -> list[Hotspot]:
    if bundle is None:
        return []
    selected = [resource for resource in resources if resource in RESOURCE_DEFINITIONS]
    if not selected:
        return []

    combined = Image.new("L", (resolution, resolution), 0)
    for resource in selected:
        mask = build_resource_mask(bundle, resource, combined.size, point_radius, blur_radius)
        combined = ImageChops.lighter(combined, mask)

    pixels = combined.load()
    candidates: list[tuple[int, int, int]] = []
    for y in range(resolution):
        for x in range(resolution):
            value = int(pixels[x, y])
            if value >= 20:
                candidates.append((value, x, y))
    candidates.sort(reverse=True)

    chosen: list[tuple[int, int, int]] = []
    separation = max(8, resolution // 10)
    for value, x, y in candidates:
        if any((x - cx) ** 2 + (y - cy) ** 2 < separation ** 2 for _cv, cx, cy in chosen):
            continue
        chosen.append((value, x, y))
        if len(chosen) >= limit:
            break

    label = " + ".join(selected)
    return [
        Hotspot(label, x / (resolution - 1), 1.0 - y / (resolution - 1), value)
        for value, x, y in chosen
    ]


def spreadsheet_column(index: int) -> str:
    index = max(0, index)
    letters = ""
    while True:
        index, remainder = divmod(index, 26)
        letters = chr(65 + remainder) + letters
        if index == 0:
            return letters
        index -= 1


def grid_reference(x_fraction: float, y_fraction: float, world_size: int, cell_size: int = 150) -> str:
    if world_size <= 0:
        return f"{x_fraction * 100:.1f}%, {y_fraction * 100:.1f}%"
    columns = max(1, math.ceil(world_size / cell_size))
    rows = columns
    column = min(columns - 1, max(0, int(x_fraction * columns)))
    row_from_top = min(rows - 1, max(0, int((1.0 - y_fraction) * rows)))
    return f"{spreadsheet_column(column)}{row_from_top}"
