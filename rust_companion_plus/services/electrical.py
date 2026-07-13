from __future__ import annotations

import itertools
import re
from collections import Counter
from dataclasses import dataclass
from math import inf
from typing import Iterable

from rust_companion_plus.catalog import electrical_catalog
from rust_companion_plus.models import ElectricalSetup, SetupComponent


NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
    "sixteen": 16,
    "twenty": 20,
}


@dataclass(slots=True)
class ParseResult:
    components: dict[str, int]
    unmatched: list[str]


@dataclass(slots=True)
class ElectricalAnalysis:
    load_rw: float
    peak_generation_rw: float
    estimated_generation_rw: float
    battery_capacity_rwm: float
    battery_output_limit_rw: float
    no_generation_runtime_minutes: float
    estimated_runtime_minutes: float
    peak_headroom_rw: float
    utilization_percent: float
    required_peak_for_charging_rw: float
    recommendations: list[str]


def _quantity_from_fragment(fragment: str, alias_start: int) -> int:
    prefix = fragment[:alias_start].strip(" :-x×")
    if not prefix:
        return 1
    digit_matches = re.findall(r"\d+", prefix)
    if digit_matches:
        return max(1, int(digit_matches[-1]))
    words = re.findall(r"[a-z]+", prefix.lower())
    for word in reversed(words):
        if word in NUMBER_WORDS:
            return NUMBER_WORDS[word]
    return 1


def parse_component_text(text: str) -> ParseResult:
    """Parse forgiving text such as '6 turrets, 4 lights and a large battery'."""
    catalog = electrical_catalog()
    aliases: list[tuple[str, str]] = []
    for name, row in catalog.items():
        for alias in row.get("aliases", []):
            aliases.append((alias.lower(), name))
    aliases.sort(key=lambda pair: len(pair[0]), reverse=True)

    normalized = text.lower().replace("\n", ",")
    fragments = [
        piece.strip()
        for piece in re.split(r",|;|\band\b|\bplus\b", normalized)
        if piece.strip()
    ]
    found: Counter[str] = Counter()
    unmatched: list[str] = []

    for fragment in fragments:
        matched_name = None
        matched_alias = None
        matched_start = 0
        for alias, name in aliases:
            match = re.search(rf"\b{re.escape(alias)}\b", fragment)
            if match:
                matched_name = name
                matched_alias = alias
                matched_start = match.start()
                break
        if matched_name is None:
            unmatched.append(fragment)
            continue
        quantity = _quantity_from_fragment(fragment, matched_start)
        found[matched_name] += quantity

        # Support "2 turrets 4 lights" even without punctuation.
        tail = fragment[matched_start + len(matched_alias or ""):].strip()
        if tail and re.search(r"\d+\s+[a-z]", tail):
            nested = parse_component_text(tail)
            found.update(nested.components)
            unmatched.extend(nested.unmatched)

    return ParseResult(dict(found), unmatched)


def merge_parsed_components(
    existing: list[SetupComponent],
    parsed: dict[str, int],
    state: str,
    zone: str = "Main",
) -> list[SetupComponent]:
    merged = [SetupComponent(**item.to_dict()) for item in existing]
    index = {
        (item.component, item.state, item.zone): item
        for item in merged
    }
    for component, quantity in parsed.items():
        key = (component, state, zone)
        if key in index:
            index[key].quantity += quantity
        else:
            item = SetupComponent(component, quantity, state, zone)
            merged.append(item)
            index[key] = item
    return merged


def _active_items(setup: ElectricalSetup) -> Iterable[SetupComponent]:
    return (
        item
        for item in setup.components
        if item.state.lower() in {"placed", "planned"} and item.quantity > 0
    )


def analyze_setup(setup: ElectricalSetup) -> ElectricalAnalysis:
    catalog = electrical_catalog()
    load = 0.0
    peak_generation = 0.0
    estimated_generation = 0.0
    capacity = 0.0
    battery_limit = 0.0

    solar_factor = min(1.0, max(0.0, setup.assumptions.get("solar_utilization", 0.35)))
    wind_factor = min(1.0, max(0.0, setup.assumptions.get("wind_utilization", 0.55)))
    charge_fraction = min(
        1.0, max(0.0, setup.assumptions.get("battery_charge_fraction", 1.0))
    )

    active_counts: Counter[str] = Counter()
    for item in _active_items(setup):
        row = catalog.get(item.component)
        if row is None:
            continue
        quantity = item.quantity
        active_counts[item.component] += quantity
        load += float(row.get("power_draw", 0)) * quantity
        peak = float(row.get("max_output", 0)) * quantity
        peak_generation += peak
        kind = row.get("generation_kind", "")
        factor = solar_factor if kind == "solar" else wind_factor if kind == "wind" else 1.0
        estimated_generation += peak * factor
        capacity += float(row.get("capacity_rwm", 0)) * quantity * charge_fraction
        battery_limit += float(row.get("output_limit", 0)) * quantity

    no_generation_runtime = inf if load <= 0 else capacity / load
    net_drain = max(0.0, load - estimated_generation)
    estimated_runtime = inf if net_drain <= 0 else capacity / net_drain
    headroom = peak_generation - load
    utilization = 0.0 if peak_generation <= 0 else (load / peak_generation) * 100.0
    required_for_charging = load / 0.8 if load > 0 else 0.0

    recommendations: list[str] = []
    if load <= 0:
        recommendations.append("Add at least one active load to analyze the design.")
    if peak_generation <= 0 and load > 0:
        recommendations.append("No generator is planned. The system will run only from stored battery charge.")
    elif peak_generation < load:
        recommendations.append(
            f"Peak generation is {load - peak_generation:.0f} rW below the active load."
        )
    if capacity <= 0 and load > 0:
        recommendations.append("Add battery storage for night-time and low-wind resilience.")
    if battery_limit > 0 and load > battery_limit:
        recommendations.append(
            f"Battery output is undersized by {load - battery_limit:.0f} rW. "
            "Split the system across more batteries or reduce simultaneous loads."
        )
    if peak_generation > load * 1.75 and load > 0:
        recommendations.append(
            "Peak generation is far above the active load. Keep the margin for expansion, "
            "or remove generation components to reduce build cost."
        )
    if estimated_generation < load and capacity > 0:
        hours = estimated_runtime / 60.0
        recommendations.append(
            f"At the current solar/wind assumptions, stored charge is estimated to last {hours:.1f} hours."
        )
    elif estimated_generation >= load and load > 0:
        recommendations.append(
            "Estimated average generation covers the load; batteries should trend toward charging."
        )
    if peak_generation < required_for_charging and capacity > 0 and load > 0:
        recommendations.append(
            f"For comfortable battery charging while powering the load, target roughly "
            f"{required_for_charging:.0f} rW or more of usable input."
        )
    if active_counts["Auto Turret"] >= 4 and active_counts["Electrical Branch"] == 0:
        recommendations.append(
            "Use electrical branches or separate battery buses so one damaged line does not disable every turret."
        )
    if active_counts["Large Solar Panel"] > 0 and active_counts["Root Combiner"] == 0:
        recommendations.append("Solar arrays usually need root combiners before feeding a battery.")
    if active_counts["Wind Turbine"] > 0:
        recommendations.append(
            "Wind output is variable and improves with height; keep the utilization slider conservative."
        )
    if not recommendations:
        recommendations.append("The current design has no obvious power-balance issue.")

    return ElectricalAnalysis(
        load_rw=load,
        peak_generation_rw=peak_generation,
        estimated_generation_rw=estimated_generation,
        battery_capacity_rwm=capacity,
        battery_output_limit_rw=battery_limit,
        no_generation_runtime_minutes=no_generation_runtime,
        estimated_runtime_minutes=estimated_runtime,
        peak_headroom_rw=headroom,
        utilization_percent=utilization,
        required_peak_for_charging_rw=required_for_charging,
        recommendations=recommendations,
    )


def component_summary(setup: ElectricalSetup) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in setup.components:
        if item.state.lower() in {"placed", "planned"}:
            counts[item.component] += item.quantity
    return counts


def compare_setups(left: ElectricalSetup, right: ElectricalSetup) -> list[str]:
    left_counts = component_summary(left)
    right_counts = component_summary(right)
    all_names = sorted(set(left_counts) | set(right_counts))
    lines = []
    for name in all_names:
        delta = right_counts[name] - left_counts[name]
        if delta:
            lines.append(f"{name}: {left_counts[name]} → {right_counts[name]} ({delta:+d})")

    left_analysis = analyze_setup(left)
    right_analysis = analyze_setup(right)
    lines.extend(
        [
            "",
            f"Load: {left_analysis.load_rw:.0f} → {right_analysis.load_rw:.0f} rW "
            f"({right_analysis.load_rw - left_analysis.load_rw:+.0f})",
            f"Peak generation: {left_analysis.peak_generation_rw:.0f} → "
            f"{right_analysis.peak_generation_rw:.0f} rW "
            f"({right_analysis.peak_generation_rw - left_analysis.peak_generation_rw:+.0f})",
            f"Battery capacity: {left_analysis.battery_capacity_rwm:.0f} → "
            f"{right_analysis.battery_capacity_rwm:.0f} rWm "
            f"({right_analysis.battery_capacity_rwm - left_analysis.battery_capacity_rwm:+.0f})",
        ]
    )
    return lines


def suggested_three_parent_crosses(plants: list[str], limit: int = 5) -> list[tuple[str, str, str, str, int]]:
    """
    Rank simple three-parent crosses.

    For each gene position, the most common parent gene wins. This is a useful
    planning heuristic, not a full simulation of every in-game crossbreeding rule.
    """
    clean = sorted({plant.strip().upper() for plant in plants if re.fullmatch(r"[GYHWX]{6}", plant.strip().upper())})
    weights = {"G": 3, "Y": 3, "H": 1, "W": -2, "X": -3}
    ranked: list[tuple[str, str, str, str, int]] = []
    for a, b, c in itertools.combinations(clean, 3):
        child = ""
        for idx in range(6):
            genes = [a[idx], b[idx], c[idx]]
            counts = Counter(genes)
            gene = max(genes, key=lambda value: (counts[value], weights[value]))
            child += gene
        score = sum(weights[gene] for gene in child)
        ranked.append((a, b, c, child, score))
    ranked.sort(key=lambda row: (row[4], row[3].count("Y"), row[3].count("G")), reverse=True)
    return ranked[:limit]
