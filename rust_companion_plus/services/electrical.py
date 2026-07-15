from __future__ import annotations

import itertools
import re
from collections import Counter
from dataclasses import dataclass
from math import ceil, inf
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
    usable_generation_rw: float
    battery_capacity_rwm: float
    battery_output_limit_rw: float
    battery_charge_efficiency: float
    no_generation_runtime_minutes: float
    estimated_runtime_minutes: float
    peak_headroom_rw: float
    average_headroom_rw: float
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
    """Analyze aggregate Rust electrical capacity using a battery-bus model.

    Renewable/fuel generation is treated as battery input when storage exists.
    Battery charge efficiency therefore applies to generation before it offsets
    active load. Without a battery, generation feeds the load directly.
    """
    catalog = electrical_catalog()
    load = 0.0
    peak_generation = 0.0
    estimated_generation = 0.0
    full_capacity = 0.0
    charged_capacity = 0.0
    battery_limit = 0.0
    weighted_efficiency = 0.0

    solar_factor = min(
        1.0,
        max(0.0, setup.assumptions.get("solar_utilization", 0.35)),
    )
    wind_factor = min(
        1.0,
        max(0.0, setup.assumptions.get("wind_utilization", 0.55)),
    )
    charge_fraction = min(
        1.0,
        max(0.0, setup.assumptions.get("battery_charge_fraction", 1.0)),
    )

    active_counts: Counter[str] = Counter()
    for item in _active_items(setup):
        row = catalog.get(item.component)
        if row is None:
            continue

        quantity = item.quantity
        active_counts[item.component] += quantity
        load += float(row.get("power_draw", 0) or 0) * quantity

        peak = float(row.get("max_output", 0) or 0) * quantity
        peak_generation += peak
        kind = str(row.get("generation_kind", "") or "")
        factor = (
            solar_factor
            if kind == "solar"
            else wind_factor
            if kind == "wind"
            else 1.0
        )
        estimated_generation += peak * factor

        item_capacity = float(row.get("capacity_rwm", 0) or 0) * quantity
        efficiency = min(
            1.0,
            max(0.0, float(row.get("charge_efficiency", 1.0) or 1.0)),
        )
        full_capacity += item_capacity
        charged_capacity += item_capacity * charge_fraction
        weighted_efficiency += item_capacity * efficiency
        battery_limit += float(row.get("output_limit", 0) or 0) * quantity

    has_storage = full_capacity > 0
    battery_efficiency = (
        weighted_efficiency / full_capacity
        if has_storage
        else 1.0
    )
    usable_peak = (
        peak_generation * battery_efficiency
        if has_storage
        else peak_generation
    )
    usable_average = (
        estimated_generation * battery_efficiency
        if has_storage
        else estimated_generation
    )

    no_generation_runtime = (
        inf
        if load <= 0
        else charged_capacity / load
    )
    net_drain = max(0.0, load - usable_average)
    estimated_runtime = (
        inf
        if load <= 0 or net_drain <= 0
        else charged_capacity / net_drain
    )
    peak_headroom = usable_peak - load
    average_headroom = usable_average - load
    utilization = (
        0.0
        if usable_peak <= 0
        else (load / usable_peak) * 100.0
    )
    required_peak_for_charging = (
        load / battery_efficiency
        if has_storage and battery_efficiency > 0
        else load
    )

    recommendations: list[str] = []

    if load <= 0:
        recommendations.append(
            "[Info] Add at least one active load to analyze the design."
        )

    if peak_generation <= 0 and load > 0:
        recommendations.append(
            "[Fix] No generator is planned. The system can run only from stored charge."
        )
    elif usable_peak < load:
        recommendations.append(
            f"[Fix] Usable peak power is {load - usable_peak:.0f} rW below the "
            "active load after battery input losses."
        )

    if charged_capacity <= 0 and load > 0:
        recommendations.append(
            "[Fix] Add rechargeable battery storage for night-time and low-wind operation."
        )

    if has_storage and battery_limit < load:
        recommendations.append(
            f"[Fix] Battery output is undersized by {load - battery_limit:.0f} rW. "
            "Use a larger battery or combine separate battery buses."
        )

    if has_storage and peak_generation > 0 and peak_generation < required_peak_for_charging:
        recommendations.append(
            f"[Fix] The battery bus needs about {required_peak_for_charging:.0f} rW "
            f"of raw input to sustain a {load:.0f} rW load at "
            f"{battery_efficiency * 100:.0f}% charging efficiency."
        )

    if load > 0 and charged_capacity > 0:
        if usable_average < load:
            recommendations.append(
                f"[Info] At the current solar/wind assumptions, stored charge lasts "
                f"about {estimated_runtime / 60.0:.1f} hours while generation is available."
            )
        else:
            recommendations.append(
                "[Info] Estimated usable average generation covers the active load; "
                "the batteries should trend toward charging."
            )

    if usable_peak > load * 2.0 and load > 0:
        recommendations.append(
            "[Optimize] Usable peak generation is more than double the active load. "
            "Keep the margin for expansion or remove excess generation."
        )

    if active_counts["Auto Turret"] >= 4 and (
        active_counts["Electrical Branch"] + active_counts["Splitter"]
    ) == 0:
        recommendations.append(
            "[Optimize] Split turret power across branches or separate buses so one "
            "damaged route does not disable every turret."
        )

    if active_counts["Large Solar Panel"] >= 2 and active_counts["Root Combiner"] == 0:
        recommendations.append(
            "[Fix] Multiple solar panels normally need chained Root Combiners before "
            "feeding a shared battery input."
        )

    if active_counts["Wind Turbine"] > 0:
        recommendations.append(
            "[Info] Wind output varies with wind speed and improves at greater height; "
            "keep the wind-average assumption conservative."
        )

    small_batteries = active_counts["Small Rechargeable Battery"]
    medium_batteries = active_counts["Medium Rechargeable Battery"]
    large_batteries = active_counts["Large Rechargeable Battery"]

    if small_batteries >= 2 and load <= 50:
        recommendations.append(
            f"[Swap] {small_batteries} small batteries provide "
            f"{small_batteries * 15} rW output and {small_batteries * 400:,} rWm capacity. "
            "One medium battery provides 50 rW and 9,000 rWm with less canvas clutter."
        )

    if medium_batteries >= 2 and load <= 100:
        recommendations.append(
            f"[Swap] {medium_batteries} medium batteries provide "
            f"{medium_batteries * 50} rW output and {medium_batteries * 9000:,} rWm capacity. "
            "For a load at or below 100 rW, one large battery provides the same 100 rW "
            "output as two mediums and increases two-medium capacity from 18,000 to 24,000 rWm."
        )

    if large_batteries > 0 and load <= 15 and no_generation_runtime > 24 * 60:
        recommendations.append(
            "[Optimize] A large battery is heavily oversized for this sub-15 rW load. "
            "If you do not need long reserve time, compare a small or medium battery."
        )

    solar_panels = active_counts["Large Solar Panel"]
    wind_turbines = active_counts["Wind Turbine"]
    small_generators = active_counts["Small Generator"]

    solar_average_raw = solar_panels * 20.0 * solar_factor
    wind_unit_average_raw = 150.0 * wind_factor
    if (
        solar_panels >= 8
        and wind_turbines == 0
        and required_peak_for_charging <= 150
        and wind_unit_average_raw * battery_efficiency >= load
    ):
        recommendations.append(
            f"[Swap] {solar_panels} solar panels provide {solar_panels * 20} rW peak "
            f"and about {solar_average_raw:.0f} rW raw average at the current assumption. "
            f"One well-elevated wind turbine provides up to 150 rW peak and about "
            f"{wind_unit_average_raw:.0f} rW raw average, so it can reduce component count."
        )

    renewable_average_usable = (
        solar_average_raw
        + wind_turbines * wind_unit_average_raw
    ) * battery_efficiency
    if (
        small_generators > 0
        and (solar_panels > 0 or wind_turbines > 0)
        and renewable_average_usable >= load
        and load > 0
    ):
        recommendations.append(
            "[Optimize] Renewable average output already covers the load under the selected "
            "assumptions. Keep the Small Generator only as emergency backup."
        )

    if (
        small_generators > 0
        and solar_panels == 0
        and wind_turbines == 0
        and load > 0
        and has_storage
    ):
        solar_unit_usable = 20.0 * solar_factor * battery_efficiency
        wind_unit_usable = 150.0 * wind_factor * battery_efficiency
        solar_needed = (
            ceil(load / solar_unit_usable)
            if solar_unit_usable > 0
            else 0
        )
        wind_needed = (
            ceil(load / wind_unit_usable)
            if wind_unit_usable > 0
            else 0
        )
        alternatives = []
        if solar_needed:
            alternatives.append(f"about {solar_needed} solar panels")
        if wind_needed:
            alternatives.append(f"about {wind_needed} wind turbine(s)")
        if alternatives:
            recommendations.append(
                "[Swap] For fuel-free average coverage at the current assumptions, compare "
                + " or ".join(alternatives)
                + "; retain the generator for emergency use."
            )

    if not recommendations:
        recommendations.append(
            "[Info] The current design has no obvious aggregate power-balance issue."
        )

    return ElectricalAnalysis(
        load_rw=load,
        peak_generation_rw=peak_generation,
        estimated_generation_rw=estimated_generation,
        usable_generation_rw=usable_average,
        battery_capacity_rwm=charged_capacity,
        battery_output_limit_rw=battery_limit,
        battery_charge_efficiency=battery_efficiency,
        no_generation_runtime_minutes=no_generation_runtime,
        estimated_runtime_minutes=estimated_runtime,
        peak_headroom_rw=peak_headroom,
        average_headroom_rw=average_headroom,
        utilization_percent=utilization,
        required_peak_for_charging_rw=required_peak_for_charging,
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
