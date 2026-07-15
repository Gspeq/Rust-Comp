from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from rust_companion_plus.services.resource_heatmaps import (
    grid_reference,
)


def world_size_for(
    snapshot: Any,
    profile_record: dict[str, Any] | None = None,
) -> int:
    if snapshot is not None:
        server = getattr(snapshot, "server", {}) or {}
        try:
            size = int(
                server.get("size")
                or server.get("map_size")
                or 0
            )
        except (TypeError, ValueError):
            size = 0
        if size > 0:
            return size

    record = (
        profile_record
        if isinstance(profile_record, dict)
        else {}
    )
    assets = (
        record.get("assets")
        if isinstance(record.get("assets"), dict)
        else {}
    )
    try:
        return max(
            0,
            int(assets.get("world_size") or 0),
        )
    except (TypeError, ValueError):
        return 0


def world_to_fraction(
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


def grid_for_world(
    x: float,
    y: float,
    world_size: int,
) -> str:
    normalized = world_to_fraction(
        x,
        y,
        world_size,
    )
    if normalized is None:
        return "?"
    return grid_reference(
        normalized[0],
        normalized[1],
        world_size,
    )


def _manifest_path(
    profile_record: dict[str, Any] | None,
) -> Path | None:
    record = (
        profile_record
        if isinstance(profile_record, dict)
        else {}
    )
    assets = (
        record.get("assets")
        if isinstance(record.get("assets"), dict)
        else {}
    )
    source = str(
        assets.get("parsed_map_dir") or ""
    ).strip()
    if not source:
        return None
    path = Path(source) / "map_resolved.json"
    return path if path.is_file() else None


def load_monument_markers(
    profile_record: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    path = _manifest_path(profile_record)
    if path is None:
        return []

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except (OSError, json.JSONDecodeError):
        return []

    monuments = payload.get("monuments")
    if not isinstance(monuments, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in monuments:
        if not isinstance(item, dict):
            continue
        try:
            fx = float(item.get("x_fraction"))
            fy = float(item.get("y_fraction"))
        except (TypeError, ValueError):
            continue
        if not (
            0.0 <= fx <= 1.0
            and 0.0 <= fy <= 1.0
        ):
            continue
        rows.append(
            {
                "x_fraction": fx,
                "y_fraction": fy,
                "label": str(
                    item.get("label")
                    or "Monument marker"
                ),
                "confidence": float(
                    item.get("confidence") or 0.0
                ),
            }
        )
    return rows


def _nearest_monument(
    x: float,
    y: float,
    *,
    world_size: int,
    monuments: list[dict[str, Any]],
) -> tuple[str, float | None]:
    normalized = world_to_fraction(
        x,
        y,
        world_size,
    )
    if normalized is None or not monuments:
        return "", None

    fx, fy = normalized
    nearest: tuple[float, dict[str, Any]] | None = None
    for monument in monuments:
        distance = math.hypot(
            fx - float(monument["x_fraction"]),
            fy - float(monument["y_fraction"]),
        ) * world_size
        if nearest is None or distance < nearest[0]:
            nearest = (distance, monument)

    if nearest is None:
        return "", None
    return (
        str(nearest[1].get("label") or "Monument marker"),
        nearest[0],
    )


def build_team_intelligence(
    snapshot: Any,
    *,
    steam_id: int,
    profile_record: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if snapshot is None:
        return [], {
            "total": 0,
            "online": 0,
            "alive": 0,
            "nearest_teammate": "",
            "nearest_distance_m": None,
            "spread_m": 0.0,
            "center_grid": "?",
            "self_grid": "?",
            "monument_markers": 0,
            "near_monument_count": 0,
        }

    world_size = world_size_for(
        snapshot,
        profile_record,
    )
    monuments = load_monument_markers(
        profile_record
    )
    members = [
        dict(item)
        for item in getattr(snapshot, "team", []) or []
        if isinstance(item, dict)
    ]

    self_member = next(
        (
            item
            for item in members
            if str(item.get("steam_id") or "")
            == str(steam_id)
        ),
        None,
    )
    self_x = (
        float(self_member.get("x", 0) or 0)
        if self_member is not None
        else None
    )
    self_y = (
        float(self_member.get("y", 0) or 0)
        if self_member is not None
        else None
    )

    rows: list[dict[str, Any]] = []
    for member in members:
        try:
            x = float(member.get("x", 0) or 0)
            y = float(member.get("y", 0) or 0)
        except (TypeError, ValueError):
            x = y = 0.0

        is_self = (
            str(member.get("steam_id") or "")
            == str(steam_id)
        )
        distance = None
        if (
            not is_self
            and self_x is not None
            and self_y is not None
        ):
            distance = math.hypot(
                x - self_x,
                y - self_y,
            )

        monument_label, monument_distance = (
            _nearest_monument(
                x,
                y,
                world_size=world_size,
                monuments=monuments,
            )
        )

        rows.append(
            {
                "name": str(
                    member.get("name")
                    or member.get("steam_id")
                    or "Unknown"
                ),
                "steam_id": str(
                    member.get("steam_id") or ""
                ),
                "is_self": is_self,
                "is_online": bool(
                    member.get("is_online")
                ),
                "is_alive": bool(
                    member.get("is_alive", True)
                ),
                "x": x,
                "y": y,
                "grid": grid_for_world(
                    x,
                    y,
                    world_size,
                ),
                "distance_m": distance,
                "monument_label": monument_label,
                "monument_distance_m": monument_distance,
                "near_monument": (
                    monument_distance is not None
                    and monument_distance <= 250.0
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            not bool(row["is_self"]),
            not bool(row["is_online"]),
            not bool(row["is_alive"]),
            str(row["name"]).casefold(),
        )
    )

    active_positions = [
        (
            float(row["x"]),
            float(row["y"]),
        )
        for row in rows
        if row["is_online"]
    ]
    spread = 0.0
    for index, first in enumerate(active_positions):
        for second in active_positions[index + 1 :]:
            spread = max(
                spread,
                math.hypot(
                    first[0] - second[0],
                    first[1] - second[1],
                ),
            )

    center_grid = "?"
    if active_positions and world_size > 0:
        center_x = sum(
            point[0] for point in active_positions
        ) / len(active_positions)
        center_y = sum(
            point[1] for point in active_positions
        ) / len(active_positions)
        center_grid = grid_for_world(
            center_x,
            center_y,
            world_size,
        )

    nearest_rows = [
        row
        for row in rows
        if row["distance_m"] is not None
    ]
    nearest = min(
        nearest_rows,
        key=lambda row: float(row["distance_m"]),
        default=None,
    )

    summary = {
        "total": len(rows),
        "online": sum(
            bool(row["is_online"])
            for row in rows
        ),
        "alive": sum(
            bool(row["is_alive"])
            for row in rows
        ),
        "nearest_teammate": (
            str(nearest["name"])
            if nearest is not None
            else ""
        ),
        "nearest_distance_m": (
            float(nearest["distance_m"])
            if nearest is not None
            else None
        ),
        "spread_m": spread,
        "center_grid": center_grid,
        "self_grid": (
            next(
                (
                    str(row["grid"])
                    for row in rows
                    if row["is_self"]
                ),
                "?",
            )
        ),
        "monument_markers": len(monuments),
        "near_monument_count": sum(
            bool(row["near_monument"])
            for row in rows
        ),
        "world_size": world_size,
    }
    return rows, summary


def compass_bearing(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
) -> tuple[float, str]:
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    degrees = (
        math.degrees(
            math.atan2(delta_x, delta_y)
        )
        + 360.0
    ) % 360.0
    directions = (
        "N",
        "NE",
        "E",
        "SE",
        "S",
        "SW",
        "W",
        "NW",
    )
    index = int(
        (degrees + 22.5) // 45.0
    ) % 8
    return degrees, directions[index]
