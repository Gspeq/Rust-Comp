from __future__ import annotations

import math
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
    "Stone": 0.27,
    "Metal": 0.18,
    "Road Access": 0.13,
    "Temperate Biome": 0.12,
    "Junk Piles": 0.08,
    "Coastline": 0.05,
    "Water": 0.03,
    "Sulfur": 0.04,
}
_NEGATIVE_WEIGHTS: dict[str, float] = {
    "Monument Proximity": 0.24,
    "Rough Terrain": 0.11,
    "Snow Biome": 0.07,
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


def recommend_starter_spots(
    bundle: ResourceHeatmapBundle | None,
    world_size: int,
    *,
    markers: Iterable[dict[str, Any]] | None = None,
    limit: int = 3,
    resolution: int = 72,
) -> list[StarterSpot]:
    """Rank plausible starter-base areas from map-derived evidence.

    This is intentionally a suitability recommendation, not a claim that a
    location is safe. Rust player activity is dynamic and is not exposed by
    the Rust+ map feed.
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

    resolution = max(36, min(128, int(resolution)))
    masks = {
        resource: _mask_values(bundle, resource, resolution)
        for resource in resources
    }

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

    candidates: list[tuple[float, int, int, dict[str, float], list[str], list[str]]] = []
    for py in range(2, resolution - 2):
        for px in range(2, resolution - 2):
            index = py * resolution + px
            evidence = {
                name: masks[name][index] / 255.0
                for name in resources
            }
            # Avoid recommending obvious water pixels.
            if evidence.get("Water", 0.0) >= 0.72:
                continue

            fx = px / (resolution - 1)
            fy = 1.0 - py / (resolution - 1)
            score = 0.42
            for name, weight in _POSITIVE_WEIGHTS.items():
                score += evidence.get(name, 0.0) * weight
            for name, weight in _NEGATIVE_WEIGHTS.items():
                score -= evidence.get(name, 0.0) * weight

            edge_distance = min(fx, fy, 1.0 - fx, 1.0 - fy)
            if edge_distance < 0.055:
                score -= 0.23
            elif edge_distance < 0.10:
                score -= 0.10

            event_distance = _nearest_distance(fx, fy, event_points)
            if event_distance < 0.08:
                score -= 0.18
            elif event_distance < 0.14:
                score -= 0.08

            shop_distance = _nearest_distance(fx, fy, shop_points)
            # A vending area is useful nearby, but building directly beside it
            # is normally high traffic.
            if 0.08 <= shop_distance <= 0.23:
                score += 0.04
            elif shop_distance < 0.045:
                score -= 0.08

            reasons: list[str] = []
            ranked_positive = sorted(
                (
                    (evidence.get(name, 0.0) * weight, name)
                    for name, weight in _POSITIVE_WEIGHTS.items()
                ),
                reverse=True,
            )
            for value, name in ranked_positive:
                if value < 0.035:
                    continue
                labels = {
                    "Stone": "good stone access",
                    "Metal": "useful metal access",
                    "Road Access": "road and component access",
                    "Temperate Biome": "temperate starter climate",
                    "Junk Piles": "nearby roadside loot potential",
                    "Coastline": "coast access",
                    "Water": "water access",
                    "Sulfur": "some sulfur potential",
                }
                reasons.append(labels.get(name, name.lower()))
                if len(reasons) >= 3:
                    break
            if 0.08 <= shop_distance <= 0.23:
                reasons.append("a shop is nearby without being directly adjacent")

            cautions: list[str] = []
            if evidence.get("Monument Proximity", 0.0) >= 0.45:
                cautions.append("closer to monument traffic")
            if evidence.get("Rough Terrain", 0.0) >= 0.55:
                cautions.append("rougher terrain may complicate building")
            if evidence.get("Snow Biome", 0.0) >= 0.50:
                cautions.append("cold-biome exposure")
            if evidence.get("Sulfur", 0.0) >= 0.70:
                cautions.append("high sulfur areas can attract geared players")
            if event_distance < 0.14:
                cautions.append("a live world event is currently nearby")
            if edge_distance < 0.10:
                cautions.append("near the map edge")

            candidates.append(
                (score, px, py, evidence, reasons, cautions)
            )

    candidates.sort(key=lambda row: row[0], reverse=True)
    selected: list[StarterSpot] = []
    minimum_separation = 0.14
    for raw_score, px, py, evidence, reasons, cautions in candidates:
        fx = px / (resolution - 1)
        fy = 1.0 - py / (resolution - 1)
        if any(
            math.hypot(fx - row.x_fraction, fy - row.y_fraction)
            < minimum_separation
            for row in selected
        ):
            continue

        normalized_score = int(round(max(0.0, min(1.0, raw_score)) * 100))
        selected.append(
            StarterSpot(
                x_fraction=round(fx, 6),
                y_fraction=round(fy, 6),
                score=normalized_score,
                grid=grid_reference(fx, fy, world_size),
                reasons=tuple(reasons or ["balanced access to the analyzed map"]),
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
