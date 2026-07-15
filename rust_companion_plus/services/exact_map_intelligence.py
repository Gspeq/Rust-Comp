from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


PARSER_VERSION = "0.2.4"


@dataclass(frozen=True, slots=True)
class ExactMapIntelligenceResult:
    output_dir: Path
    monuments_file: Path
    monument_count: int
    world_size: int
    parser_version: str = PARSER_VERSION


def monument_radius(
    row: dict[str, Any],
) -> float:
    metadata = (
        row.get("metadata")
        if isinstance(row.get("metadata"), dict)
        else {}
    )
    classification = (
        metadata.get("classification")
        if isinstance(
            metadata.get("classification"),
            dict,
        )
        else {}
    )
    gameplay = (
        metadata.get("gameplay")
        if isinstance(
            metadata.get("gameplay"),
            dict,
        )
        else {}
    )
    kind = str(
        classification.get("kind") or ""
    ).casefold()
    size_class = str(
        classification.get("size_class") or ""
    ).casefold()

    radius = {
        "small": 170.0,
        "medium": 250.0,
        "large": 360.0,
    }.get(size_class, 210.0)

    if kind == "cave":
        radius = min(radius, 130.0)
    elif "tunnel" in kind:
        radius = min(radius, 150.0)

    if bool(gameplay.get("safe_zone")):
        radius = max(radius, 300.0)
    return radius


def normalize_monuments(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("monuments", []) or []:
        if not isinstance(raw, dict):
            continue
        position = (
            raw.get("position")
            if isinstance(raw.get("position"), dict)
            else {}
        )
        try:
            x = float(position.get("x"))
            y = float(position.get("z"))
        except (TypeError, ValueError):
            continue

        metadata = (
            raw.get("metadata")
            if isinstance(raw.get("metadata"), dict)
            else {}
        )
        classification = (
            metadata.get("classification")
            if isinstance(
                metadata.get("classification"),
                dict,
            )
            else {}
        )
        gameplay = (
            metadata.get("gameplay")
            if isinstance(
                metadata.get("gameplay"),
                dict,
            )
            else {}
        )
        display_name = str(
            metadata.get("display_name")
            or raw.get("name")
            or "Unnamed Monument"
        ).strip()

        row = {
            "name": display_name,
            "internal_name": str(
                raw.get("name") or ""
            ),
            "prefab_path": str(
                raw.get("prefab_path") or ""
            ),
            "x": x,
            "y": y,
            "heading_degrees": float(
                raw.get("heading_degrees") or 0.0
            ),
            "kind": str(
                classification.get("kind")
                or "monument"
            ),
            "environment": str(
                classification.get("environment")
                or ""
            ),
            "size_class": str(
                classification.get("size_class")
                or ""
            ),
            "safe_zone": bool(
                gameplay.get("safe_zone")
            ),
            "recycler_count": int(
                gameplay.get("recycler_count") or 0
            ),
            "keycard_requirements": [
                str(item)
                for item in (
                    gameplay.get(
                        "keycard_requirements"
                    )
                    or []
                )
                if str(item).strip()
            ],
            "puzzle_type": str(
                gameplay.get("puzzle_type")
                or "none"
            ),
            "loot_tier": int(
                gameplay.get("loot_tier") or 0
            ),
        }
        row["radius_m"] = monument_radius(raw)
        rows.append(row)

    rows.sort(
        key=lambda row: (
            str(row["name"]).casefold(),
            float(row["x"]),
            float(row["y"]),
        )
    )
    return rows


def load_normalized_monuments(
    path: str | Path,
) -> tuple[list[dict[str, Any]], int]:
    source = Path(path)
    payload = json.loads(
        source.read_text(encoding="utf-8-sig")
    )
    world_size = int(
        (
            payload.get("map")
            if isinstance(payload.get("map"), dict)
            else {}
        ).get("world_size")
        or 0
    )
    return normalize_monuments(payload), world_size


def _write_monument_proximity_layer(
    monuments: list[dict[str, Any]],
    *,
    output_dir: Path,
    world_size: int,
    resolution: int = 640,
) -> Path:
    size = max(128, int(resolution))
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)

    if world_size > 0:
        half = world_size / 2.0
        for row in monuments:
            x = float(row["x"])
            y = float(row["y"])
            fx = (x + half) / world_size
            fy = (y + half) / world_size
            if not (
                -0.05 <= fx <= 1.05
                and -0.05 <= fy <= 1.05
            ):
                continue

            radius_m = float(
                row.get("radius_m") or 200.0
            )
            radius_px = max(
                4.0,
                radius_m / world_size * size,
            )
            center_x = fx * size
            center_y = (1.0 - fy) * size
            draw.ellipse(
                (
                    center_x - radius_px,
                    center_y - radius_px,
                    center_x + radius_px,
                    center_y + radius_px,
                ),
                fill=215,
            )

    path = output_dir / "heatmap_monument_proximity.png"
    mask.save(path, format="PNG", optimize=True)
    return path


def export_exact_map_intelligence(
    raw_map_path: str | Path,
    output_dir: str | Path,
) -> ExactMapIntelligenceResult:
    """Parse exact monument identities and positions from a Rust .map file."""
    try:
        from rustmap_parser import (
            ExportConfig,
            ExportOptions,
            RustMapExporter,
        )
        from rustmap_parser import __version__ as parser_version
    except ImportError as exc:
        raise RuntimeError(
            "The built-in exact map parser is unavailable. "
            "Install rust-map-parser==0.2.4."
        ) from exc

    raw_map = Path(raw_map_path).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    exact_output = output / "exact_map"
    if exact_output.exists():
        shutil.rmtree(
            exact_output,
            ignore_errors=True,
        )
    exact_output.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = RustMapExporter(
        ExportConfig(
            map_path=raw_map,
            output_dir=exact_output,
            exports=ExportOptions(
                monuments=True,
            ),
        )
    ).run()

    source_monuments = (
        Path(result.monuments_file)
        if result.monuments_file is not None
        else exact_output / "monuments.json"
    )
    if not source_monuments.is_file():
        raise RuntimeError(
            "The exact map parser completed without monuments.json."
        )

    monuments_file = output / "monuments.json"
    shutil.copy2(
        source_monuments,
        monuments_file,
    )
    monuments, detected_world_size = (
        load_normalized_monuments(
            monuments_file
        )
    )
    world_size = int(
        detected_world_size
        or result.world_size
        or 0
    )

    normalized_path = output / "named_monuments.json"
    normalized_payload = {
        "schema_version": 1,
        "parser": {
            "name": "rust-map-parser",
            "version": str(
                parser_version or PARSER_VERSION
            ),
        },
        "world_size": world_size,
        "count": len(monuments),
        "monuments": monuments,
    }
    normalized_path.write_text(
        json.dumps(
            normalized_payload,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
        newline="\n",
    )

    proximity_path = _write_monument_proximity_layer(
        monuments,
        output_dir=output,
        world_size=world_size,
    )

    manifest_path = output / "map_resolved.json"
    try:
        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8-sig"
            )
        )
    except (OSError, json.JSONDecodeError):
        manifest = {}

    layers = (
        dict(manifest.get("layers"))
        if isinstance(
            manifest.get("layers"),
            dict,
        )
        else {}
    )
    layers["Monument Proximity"] = (
        proximity_path.name
    )
    manifest["layers"] = layers
    manifest["exact_parser"] = {
        "status": "ready",
        "name": "rust-map-parser",
        "version": str(
            parser_version or PARSER_VERSION
        ),
        "raw_map_path": str(raw_map),
        "monuments_file": monuments_file.name,
        "normalized_monuments_file": (
            normalized_path.name
        ),
        "monument_count": len(monuments),
        "world_size": world_size,
    }
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
        newline="\n",
    )

    return ExactMapIntelligenceResult(
        output_dir=output,
        monuments_file=monuments_file,
        monument_count=len(monuments),
        world_size=world_size,
        parser_version=str(
            parser_version or PARSER_VERSION
        ),
    )
