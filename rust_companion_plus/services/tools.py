from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from rust_companion_plus.catalog import BUILDING_COSTS, GENE_WEIGHTS, RECYCLE_CATALOG


def calculate_upkeep_hours(
    inventory: dict[str, float], hourly_cost: dict[str, float]
) -> tuple[float, dict[str, float]]:
    remaining: dict[str, float] = {}
    limits = []
    for resource, cost in hourly_cost.items():
        if cost <= 0:
            continue
        hours = max(0.0, inventory.get(resource, 0.0)) / cost
        remaining[resource] = hours
        limits.append(hours)
    return (min(limits) if limits else float("inf"), remaining)


def calculate_recycle(item: str, quantity: int) -> dict[str, float]:
    return {
        resource: amount * max(0, quantity)
        for resource, amount in RECYCLE_CATALOG.get(item, {}).items()
    }


def calculate_building_cost(counts: dict[str, int]) -> dict[str, int]:
    total: defaultdict[str, int] = defaultdict(int)
    for grade, count in counts.items():
        for resource, amount in BUILDING_COSTS.get(grade, {}).items():
            total[resource] += amount * max(0, count)
    return dict(total)


def score_genes(genes: str) -> int:
    genes = genes.strip().upper()
    if len(genes) != 6 or any(gene not in GENE_WEIGHTS for gene in genes):
        raise ValueError("Genes must contain exactly six letters using G, Y, H, W or X.")
    return sum(GENE_WEIGHTS[gene] for gene in genes)


def rank_plants(plants: Iterable[str]) -> list[tuple[str, int]]:
    unique = {plant.strip().upper() for plant in plants if plant.strip()}
    ranked = [(plant, score_genes(plant)) for plant in unique]
    return sorted(
        ranked,
        key=lambda row: (row[1], row[0].count("Y"), row[0].count("G")),
        reverse=True,
    )
