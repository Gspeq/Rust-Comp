from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from rust_companion_plus.services.resource_heatmaps import (
    grid_reference,
)


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    """Normalize optional parser metadata without raising."""
    if value is None:
        return int(default)
    if isinstance(value, bool):
        return int(value)

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return int(default)

    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        try:
            return int(float(value))
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return int(default)

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


def _parsed_map_dir(
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
    path = Path(source)
    return path if path.is_dir() else None


def load_named_monuments(
    profile_record: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    source = _parsed_map_dir(profile_record)
    if source is None:
        return []

    normalized = source / "named_monuments.json"
    if normalized.is_file():
        try:
            payload = json.loads(
                normalized.read_text(
                    encoding="utf-8-sig"
                )
            )
        except (OSError, json.JSONDecodeError):
            payload = {}
        rows = payload.get("monuments")
        if isinstance(rows, list):
            return [
                dict(row)
                for row in rows
                if isinstance(row, dict)
            ]

    monuments = source / "monuments.json"
    if not monuments.is_file():
        return []

    try:
        payload = json.loads(
            monuments.read_text(
                encoding="utf-8-sig"
            )
        )
    except (OSError, json.JSONDecodeError):
        return []

    rows: list[dict[str, Any]] = []
    for raw in payload.get("monuments", []) or []:
        if not isinstance(raw, dict):
            continue
        position = (
            raw.get("position")
            if isinstance(raw.get("position"), dict)
            else {}
        )
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
        try:
            x = float(position.get("x"))
            y = float(position.get("z"))
        except (TypeError, ValueError):
            continue

        size_class = str(
            classification.get("size_class")
            or ""
        ).casefold()
        radius = {
            "small": 170.0,
            "medium": 250.0,
            "large": 360.0,
        }.get(size_class, 210.0)
        if bool(gameplay.get("safe_zone")):
            radius = max(radius, 300.0)

        rows.append(
            {
                "name": str(
                    metadata.get("display_name")
                    or raw.get("name")
                    or "Unnamed Monument"
                ),
                "x": x,
                "y": y,
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
                    gameplay.get("recycler_count")
                    or 0
                ),
                "keycard_requirements": [
                    str(item)
                    for item in (
                        gameplay.get(
                            "keycard_requirements"
                        )
                        or []
                    )
                ],
                "puzzle_type": str(
                    gameplay.get("puzzle_type")
                    or "none"
                ),
                "loot_tier": int(
                    gameplay.get("loot_tier")
                    or 0
                ),
                "radius_m": radius,
            }
        )
    return rows


def _nearest_monument(
    x: float,
    y: float,
    monuments: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, float | None]:
    nearest: tuple[
        float,
        dict[str, Any],
    ] | None = None
    for monument in monuments:
        try:
            distance = math.hypot(
                x - float(monument["x"]),
                y - float(monument["y"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if nearest is None or distance < nearest[0]:
            nearest = (distance, monument)

    if nearest is None:
        return None, None
    return dict(nearest[1]), float(nearest[0])


def _nearest_teammate(
    member: dict[str, Any],
    members: list[dict[str, Any]],
) -> tuple[str, float | None]:
    source_id = str(member.get("steam_id") or "")
    source_x = float(member.get("x", 0) or 0)
    source_y = float(member.get("y", 0) or 0)
    nearest: tuple[float, str] | None = None

    for candidate in members:
        candidate_id = str(
            candidate.get("steam_id") or ""
        )
        if (
            not candidate_id
            or candidate_id == source_id
            or not bool(candidate.get("is_online"))
        ):
            continue
        distance = math.hypot(
            source_x
            - float(candidate.get("x", 0) or 0),
            source_y
            - float(candidate.get("y", 0) or 0),
        )
        name = str(
            candidate.get("name")
            or candidate_id
            or "Unknown"
        )
        if nearest is None or distance < nearest[0]:
            nearest = (distance, name)

    if nearest is None:
        return "", None
    return nearest[1], nearest[0]


def _monument_facts(
    monument: dict[str, Any] | None,
) -> str:
    if not monument:
        return ""

    facts: list[str] = []
    if bool(monument.get("safe_zone")):
        facts.append("Safe zone")

    recyclers = _safe_int(
        monument.get("recycler_count")
    )
    if recyclers:
        facts.append(
            f"{recyclers} recycler"
            + ("s" if recyclers != 1 else "")
        )

    cards = [
        str(item).title()
        for item in (
            monument.get(
                "keycard_requirements"
            )
            or []
        )
        if str(item).strip()
    ]
    if cards:
        facts.append(
            "Cards: " + " + ".join(cards)
        )

    loot_tier = _safe_int(
        monument.get("loot_tier")
    )
    if loot_tier:
        facts.append(f"Loot tier {loot_tier}")

    size_class = str(
        monument.get("size_class") or ""
    ).strip()
    if size_class:
        facts.append(size_class.title())

    return " · ".join(facts)


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
            "spread_m": 0.0,
            "center_grid": "?",
            "self_grid": "?",
            "named_monument_count": 0,
            "at_monument_count": 0,
            "occupied_monument_count": 0,
            "safe_zone_count": 0,
            "self_monument_name": "",
            "isolated_members": [],
            "monument_groups": {},
        }

    world_size = world_size_for(
        snapshot,
        profile_record,
    )
    monuments = load_named_monuments(
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
        distance_from_self = None
        if (
            not is_self
            and self_x is not None
            and self_y is not None
        ):
            distance_from_self = math.hypot(
                x - self_x,
                y - self_y,
            )

        nearest_monument, monument_distance = (
            _nearest_monument(
                x,
                y,
                monuments,
            )
        )
        radius = (
            float(
                nearest_monument.get("radius_m")
                or 210.0
            )
            if nearest_monument is not None
            else 0.0
        )
        at_monument = bool(
            monument_distance is not None
            and monument_distance <= radius
        )

        nearest_name, nearest_distance = (
            _nearest_teammate(
                {
                    **member,
                    "x": x,
                    "y": y,
                },
                members,
            )
        )
        isolated = bool(
            member.get("is_online")
            and nearest_distance is not None
            and nearest_distance > 500.0
        )

        row = {
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
            "distance_m": distance_from_self,
            "nearest_teammate": nearest_name,
            "nearest_teammate_distance_m": (
                nearest_distance
            ),
            "isolated": isolated,
            "monument_name": (
                str(
                    nearest_monument.get("name")
                    or ""
                )
                if nearest_monument is not None
                else ""
            ),
            "monument_distance_m": monument_distance,
            "monument_radius_m": radius,
            "at_monument": at_monument,
            "monument_facts": _monument_facts(
                nearest_monument
            ),
            "monument_safe_zone": bool(
                nearest_monument.get("safe_zone")
                if nearest_monument
                else False
            ),
            "monument_recycler_count": _safe_int(
                nearest_monument.get(
                    "recycler_count"
                )
                if nearest_monument
                else 0
            ),
            "monument_keycards": list(
                nearest_monument.get(
                    "keycard_requirements"
                )
                or []
            )
            if nearest_monument
            else [],
            "monument_loot_tier": _safe_int(
                nearest_monument.get("loot_tier")
                if nearest_monument
                else 0
            ),
        }
        rows.append(row)

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

    monument_groups: dict[str, list[str]] = {}
    for row in rows:
        if (
            not row["is_online"]
            or not row["at_monument"]
        ):
            continue
        name = str(row["monument_name"])
        monument_groups.setdefault(
            name,
            [],
        ).append(str(row["name"]))

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
        "spread_m": spread,
        "center_grid": center_grid,
        "self_grid": next(
            (
                str(row["grid"])
                for row in rows
                if row["is_self"]
            ),
            "?",
        ),
        "named_monument_count": len(monuments),
        "at_monument_count": sum(
            bool(
                row["is_online"]
                and not row["is_self"]
                and row["at_monument"]
            )
            for row in rows
        ),
        "occupied_monument_count": len(
            {
                str(row["monument_name"])
                for row in rows
                if (
                    row["is_online"]
                    and row["at_monument"]
                    and str(
                        row["monument_name"]
                    ).strip()
                )
            }
        ),
        "safe_zone_count": sum(
            bool(
                row["is_online"]
                and not row["is_self"]
                and row["at_monument"]
                and row["monument_safe_zone"]
            )
            for row in rows
        ),
        "self_monument_name": next(
            (
                str(row["monument_name"])
                for row in rows
                if (
                    row["is_self"]
                    and row["at_monument"]
                )
            ),
            "",
        ),
        "isolated_members": [
            str(row["name"])
            for row in rows
            if row["isolated"]
        ],
        "monument_groups": monument_groups,
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
