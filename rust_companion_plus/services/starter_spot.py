from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable

from PIL import Image

from rust_companion_plus.services.resource_heatmaps import (
    RESOURCE_DEFINITIONS,
    ResourceHeatmapBundle,
    build_resource_mask,
    grid_reference,
)


@dataclass(frozen=True, slots=True)
class StarterSpot:
    x_fraction: float
    y_fraction: float
    score: int
    grid: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    cautions: tuple[str, ...] = field(default_factory=tuple)
    evidence: dict[str, float] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        reason = "; ".join(self.reasons) or "balanced map position"
        caution = (
            " Caution: " + "; ".join(self.cautions)
            if self.cautions
            else ""
        )
        return f"{self.grid} · score {self.score}/100 · {reason}.{caution}"


_POSITIVE_WEIGHTS: dict[str, float] = {
    "Stone": 0.23,
    "Metal": 0.18,
    "Road Access": 0.18,
    "Temperate Biome": 0.12,
    "Junk Piles": 0.08,
    "Sulfur": 0.04,
    "Water": 0.015,
}
_NEGATIVE_WEIGHTS: dict[str, float] = {
    "Monument Proximity": 0.23,
    "Rough Terrain": 0.16,
    "Snow Biome": 0.08,
    "Coastline": 0.05,
}


def _mask_values(
    bundle: ResourceHeatmapBundle,
    resource: str,
    resolution: int,
) -> list[int]:
    if resource not in RESOURCE_DEFINITIONS:
        return [0] * (resolution * resolution)
    mask = build_resource_mask(
        bundle,
        resource,
        (resolution, resolution),
        point_radius=max(2, resolution // 36),
        blur_radius=max(2, resolution // 24),
    ).convert("L")
    return list(mask.getdata())


def _marker_fraction(
    marker: dict[str, Any],
    world_size: int,
) -> tuple[float, float] | None:
    try:
        x = float(marker.get("x", 0) or 0)
        y = float(marker.get("y", 0) or 0)
    except (TypeError, ValueError):
        return None
    if world_size <= 0:
        return None
    half = world_size / 2.0
    if x < 0 or y < 0:
        fx = (x + half) / world_size
        fy = (y + half) / world_size
    else:
        fx = x / world_size
        fy = y / world_size
    if not (-0.05 <= fx <= 1.05 and -0.05 <= fy <= 1.05):
        return None
    return min(1.0, max(0.0, fx)), min(1.0, max(0.0, fy))


def _nearest_distance(
    x: float,
    y: float,
    points: Iterable[tuple[float, float]],
) -> float:
    return min(
        (math.hypot(x - px, y - py) for px, py in points),
        default=9.0,
    )


def _local_average(
    values: list[int],
    resolution: int,
    px: int,
    py: int,
    radius: int,
) -> float:
    samples: list[float] = []
    for y in range(max(0, py - radius), min(resolution, py + radius + 1)):
        for x in range(max(0, px - radius), min(resolution, px + radius + 1)):
            samples.append(values[y * resolution + x] / 255.0)
    return sum(samples) / len(samples) if samples else 0.0


def _land_components(
    water_values: list[int],
    resolution: int,
) -> tuple[list[int], dict[int, int], int]:
    """Label connected landmasses so remote islands can be rejected."""
    if not any(water_values):
        labels = [1] * (resolution * resolution)
        return labels, {1: resolution * resolution}, 1

    land = [
        value / 255.0 < 0.43
        for value in water_values
    ]
    labels = [0] * (resolution * resolution)
    sizes: dict[int, int] = {}
    component = 0

    for index, is_land in enumerate(land):
        if not is_land or labels[index]:
            continue
        component += 1
        queue: deque[int] = deque([index])
        labels[index] = component
        size = 0
        while queue:
            current = queue.popleft()
            size += 1
            x = current % resolution
            y = current // resolution
            for nx, ny in (
                (x - 1, y),
                (x + 1, y),
                (x, y - 1),
                (x, y + 1),
            ):
                if not (0 <= nx < resolution and 0 <= ny < resolution):
                    continue
                neighbor = ny * resolution + nx
                if land[neighbor] and labels[neighbor] == 0:
                    labels[neighbor] = component
                    queue.append(neighbor)
        sizes[component] = size

    largest = max(sizes, key=sizes.get) if sizes else 0
    return labels, sizes, largest


def recommend_starter_spots(
    bundle: ResourceHeatmapBundle | None,
    world_size: int,
    *,
    markers: Iterable[dict[str, Any]] | None = None,
    limit: int = 3,
    resolution: int = 72,
) -> list[StarterSpot]:
    """Rank practical starter-base areas with mainland and escape-route checks.

    The result remains an estimate because Rust+ does not expose live player
    density, but isolated islands and water-locked cells are no longer allowed
    to win merely because they contain good resource pixels.
    """
    if bundle is None or world_size <= 0:
        return []

    available = set(bundle.resources)
    resources = [
        name
        for name in (*_POSITIVE_WEIGHTS, *_NEGATIVE_WEIGHTS)
        if name in available
    ]
    if not resources:
        return []

    resolution = max(48, min(128, int(resolution)))
    masks = {
        resource: _mask_values(bundle, resource, resolution)
        for resource in resources
    }
    water_values = masks.get(
        "Water",
        [0] * (resolution * resolution),
    )
    component_labels, component_sizes, largest_component = _land_components(
        water_values,
        resolution,
    )
    largest_size = component_sizes.get(largest_component, 0)
    total_land = sum(component_sizes.values())
    minimum_viable_landmass = max(
        int(total_land * 0.08),
        int(largest_size * 0.34),
        20,
    )

    marker_rows = [
        marker
        for marker in markers or []
        if isinstance(marker, dict)
    ]
    event_points: list[tuple[float, float]] = []
    shop_points: list[tuple[float, float]] = []
    for marker in marker_rows:
        point = _marker_fraction(marker, world_size)
        if point is None:
            continue
        marker_type = int(marker.get("type", 0) or 0)
        if marker_type in {4, 5, 6, 8}:
            event_points.append(point)
        elif marker_type == 3:
            shop_points.append(point)

    candidates: list[
        tuple[
            float,
            int,
            int,
            dict[str, float],
            list[str],
            list[str],
        ]
    ] = []

    for py in range(3, resolution - 3):
        for px in range(3, resolution - 3):
            index = py * resolution + px
            evidence = {
                name: masks[name][index] / 255.0
                for name in resources
            }
            water_here = evidence.get("Water", 0.0)
            local_water = _local_average(
                water_values,
                resolution,
                px,
                py,
                radius=max(2, resolution // 30),
            )
            component = component_labels[index]
            component_size = component_sizes.get(component, 0)
            is_mainland = bool(
                component
                and component == largest_component
            )
            substantial_landmass = component_size >= minimum_viable_landmass

            if (
                water_here >= 0.58
                or local_water >= 0.43
                or not substantial_landmass
            ):
                continue

            fx = px / (resolution - 1)
            fy = 1.0 - py / (resolution - 1)

            road = evidence.get("Road Access", 0.0)
            stone = evidence.get("Stone", 0.0)
            metal = evidence.get("Metal", 0.0)
            rough = evidence.get("Rough Terrain", 0.0)

            # Require practical access instead of allowing one resource spike to
            # carry an otherwise awkward or isolated build location.
            if road < 0.08 and max(stone, metal) < 0.18:
                continue
            if rough >= 0.82:
                continue

            score = 0.30
            for name, weight in _POSITIVE_WEIGHTS.items():
                score += evidence.get(name, 0.0) * weight
            for name, weight in _NEGATIVE_WEIGHTS.items():
                score -= evidence.get(name, 0.0) * weight

            if is_mainland:
                score += 0.12
            else:
                component_ratio = (
                    component_size / largest_size
                    if largest_size
                    else 0.0
                )
                score -= 0.14 + max(0.0, 0.55 - component_ratio) * 0.30

            score -= local_water * 0.28

            edge_distance = min(fx, fy, 1.0 - fx, 1.0 - fy)
            if edge_distance < 0.065:
                score -= 0.28
            elif edge_distance < 0.12:
                score -= 0.12

            event_distance = _nearest_distance(fx, fy, event_points)
            if event_distance < 0.08:
                score -= 0.20
            elif event_distance < 0.15:
                score -= 0.09

            shop_distance = _nearest_distance(fx, fy, shop_points)
            if 0.09 <= shop_distance <= 0.20 and road >= 0.12:
                score += 0.02
            elif shop_distance < 0.05:
                score -= 0.10

            reasons: list[str] = []
            if is_mainland:
                reasons.append("mainland access and multiple escape routes")
            ranked_positive = sorted(
                (
                    (evidence.get(name, 0.0) * weight, name)
                    for name, weight in _POSITIVE_WEIGHTS.items()
                ),
                reverse=True,
            )
            labels = {
                "Stone": "good stone access",
                "Metal": "useful metal access",
                "Road Access": "road and component access",
                "Temperate Biome": "temperate starter climate",
                "Junk Piles": "nearby roadside loot potential",
                "Water": "limited nearby water access",
                "Sulfur": "some sulfur potential",
            }
            for value, name in ranked_positive:
                if value < 0.035:
                    continue
                label = labels.get(name, name.lower())
                if label not in reasons:
                    reasons.append(label)
                if len(reasons) >= 4:
                    break

            cautions: list[str] = []
            if not is_mainland:
                cautions.append("separate landmass may limit escape routes")
            if local_water >= 0.24:
                cautions.append("water or coastline reduces nearby buildable area")
            if evidence.get("Monument Proximity", 0.0) >= 0.45:
                cautions.append("closer to monument traffic")
            if rough >= 0.55:
                cautions.append("rougher terrain may complicate building")
            if evidence.get("Snow Biome", 0.0) >= 0.50:
                cautions.append("cold-biome exposure")
            if evidence.get("Sulfur", 0.0) >= 0.70:
                cautions.append("high sulfur areas can attract geared players")
            if event_distance < 0.15:
                cautions.append("a live world event is currently nearby")
            if edge_distance < 0.12:
                cautions.append("near the map edge")

            candidates.append(
                (score, px, py, evidence, reasons, cautions)
            )

    candidates.sort(key=lambda row: row[0], reverse=True)
    selected: list[StarterSpot] = []
    minimum_separation = 0.13
    for raw_score, px, py, evidence, reasons, cautions in candidates:
        if raw_score < 0.42:
            continue
        fx = px / (resolution - 1)
        fy = 1.0 - py / (resolution - 1)
        if any(
            math.hypot(
                fx - row.x_fraction,
                fy - row.y_fraction,
            )
            < minimum_separation
            for row in selected
        ):
            continue

        normalized_score = int(
            round(max(0.0, min(1.0, raw_score)) * 100)
        )
        selected.append(
            StarterSpot(
                x_fraction=round(fx, 6),
                y_fraction=round(fy, 6),
                score=normalized_score,
                grid=grid_reference(fx, fy, world_size),
                reasons=tuple(
                    reasons
                    or ["balanced mainland access to the analyzed map"]
                ),
                cautions=tuple(cautions),
                evidence={
                    name: round(value, 3)
                    for name, value in evidence.items()
                    if value >= 0.05
                },
            )
        )
        if len(selected) >= max(1, int(limit)):
            break

    return selected
