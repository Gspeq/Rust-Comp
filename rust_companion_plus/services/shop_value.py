from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


HISTORY_VERSION = 4
MAX_HISTORY_SAMPLES = 120


@dataclass(frozen=True, slots=True)
class ItemValueProfile:
    tier: int
    tier_name: str
    actionable: bool
    common: bool
    category: str = "unknown"
    urgency: float = 0.0


@dataclass(frozen=True, slots=True)
class DealScore:
    score: int
    label: str
    unit_cost: float
    benchmark: float
    discount_fraction: float
    confidence: str
    peer_count: int = 0
    history_count: int = 0
    peer_rank: int = 0
    anomaly_score: float = 0.0
    reason: str = ""
    alert_level: str = ""
    item_tier: int = 0
    item_tier_name: str = "Common"
    actionable: bool = False
    payment_tier: int = 0
    unique_shop_count: int = 0
    market_spread: float = 0.0
    blueprint_penalty: bool = False


@dataclass(frozen=True, slots=True)
class ScoredShopRow:
    row: Any
    deal: DealScore


# Exact normalized names are preferred over broad substring checks. This avoids
# mistakes such as classifying "Rocket Launcher" as an endgame rocket or
# "Stone Barricade" as ordinary Stones.
_ENDGAME_NAMES = {
    "m249",
    "multiple grenade launcher",
    "timed explosive charge",
    "c4",
    "rocket",
    "explosive 5.56 rifle ammo",
    "explosive 5.56",
    "incendiary rocket",
    "high velocity rocket",
    "supply signal",
    "hmlmg",
}
_HIGH_NAMES = {
    "assault rifle",
    "lr-300 assault rifle",
    "lr-300",
    "lr300",
    "mp5a4",
    "mp5",
    "l96 rifle",
    "bolt action rifle",
    "m39 rifle",
    "rocket launcher",
    "auto turret",
    "sam site",
    "armored door",
    "armored double door",
    "metal facemask",
    "metal chest plate",
    "heavy plate helmet",
    "heavy plate jacket",
    "heavy plate pants",
    "night vision goggles",
    "spas-12 shotgun",
    "m92 pistol",
    "prototype 17",
    "minigun",
}
_MID_EQUIPMENT_NAMES = {
    "garage door",
    "wind turbine",
    "large rechargeable battery",
    "large battery",
    "semi-automatic rifle",
    "semi automatic rifle",
    "semi-automatic pistol",
    "semi automatic pistol",
    "thompson",
    "custom smg",
    "python revolver",
    "pump shotgun",
    "flame turret",
    "shotgun trap",
    "smart switch",
    "smart alarm",
    "storage monitor",
    "industrial conveyor",
    "industrial crafter",
    "computer station",
    "cctv camera",
    "targeting computer",
}
_RARE_COMPONENT_NAMES = {
    "rifle body",
    "smg body",
    "semi automatic body",
    "semi-automatic body",
    "tech trash",
    "targeting computer",
    "cctv camera",
}
_COMPONENT_NAMES = {
    "gears",
    "metal pipe",
    "road signs",
    "sheet metal",
    "sewing kit",
    "rope",
    "tarp",
    "metal spring",
    "electric fuse",
}
_EARLY_NAMES = {
    "revolver",
    "double barrel shotgun",
    "double barrel",
    "waterpipe shotgun",
    "crossbow",
    "hazmat suit",
    "medical syringe",
    "satchel charge",
    "bean can grenade",
    "small rechargeable battery",
    "medium rechargeable battery",
    "salvaged sword",
    "salvaged cleaver",
}
_COMMON_NAMES = {
    "hunting bow",
    "compound bow",
    "wooden arrow",
    "bone arrow",
    "fire arrow",
    "nailgun",
    "stone pickaxe",
    "stone hatchet",
    "wood",
    "stones",
    "stone",
    "cloth",
    "leather",
    "bone fragments",
    "animal fat",
    "charcoal",
    "metal fragments",
    "low grade fuel",
    "crude oil",
    "water",
    "corn",
    "pumpkin",
    "mushroom",
    "potato",
    "apple",
    "chicken breast",
    "chicken",
    "wolf meat",
    "bear meat",
    "building plan",
    "hammer",
    "torch",
    "camp fire",
    "campfire",
    "scrap tea",
    "wood tea",
    "ore tea",
}

_STRATEGIC_PAYMENT_NAMES = {
    "high quality metal",
    "hqm",
    "sulfur ore",
    "sulfur",
    "gun powder",
    "gunpowder",
    "explosives",
    "scrap",
    "tech trash",
    "targeting computer",
    "cctv camera",
    "rifle body",
    "smg body",
    "semi automatic body",
    "semi-automatic body",
}
_COMPONENT_PAYMENT_NAMES = _COMPONENT_NAMES | _RARE_COMPONENT_NAMES


def _normalized_name(value: Any) -> str:
    text = " ".join(
        re.sub(r"[^a-z0-9.+-]+", " ", str(value or "").casefold()).split()
    )
    if text.startswith("bp "):
        text = text[3:].strip()
    if text.endswith(" blueprint"):
        text = text[: -len(" blueprint")].strip()
    return text


def item_value_profile(name: Any, item_id: Any = 0) -> ItemValueProfile:
    """Classify strategic value without pretending unrelated barter is fungible."""
    text = _normalized_name(name)
    _ = item_id

    if text in _ENDGAME_NAMES:
        return ItemValueProfile(4, "Endgame", True, False, "endgame", 1.0)
    if text in _HIGH_NAMES:
        return ItemValueProfile(3, "High tier", True, False, "high equipment", 0.95)
    if text in _RARE_COMPONENT_NAMES:
        return ItemValueProfile(2, "Mid tier", True, False, "rare component", 0.88)
    if text in _MID_EQUIPMENT_NAMES:
        return ItemValueProfile(2, "Mid tier", True, False, "mid equipment", 0.78)
    if text in _COMPONENT_NAMES:
        return ItemValueProfile(2, "Mid tier", True, False, "component", 0.62)
    if text in _EARLY_NAMES:
        return ItemValueProfile(1, "Early progression", False, False, "early", 0.35)
    if text in _COMMON_NAMES:
        return ItemValueProfile(0, "Common / primitive", False, True, "common", 0.0)

    # Conservative fallback: unknown goods may be ranked by relative price but
    # cannot create urgent alerts until explicitly classified or watched.
    return ItemValueProfile(
        1,
        "Unclassified progression",
        False,
        False,
        "unclassified",
        0.20,
    )


def payment_value_tier(name: Any) -> int:
    text = _normalized_name(name)
    if text in _ENDGAME_NAMES or text in _HIGH_NAMES:
        return 3
    if text in _STRATEGIC_PAYMENT_NAMES:
        return 2
    if text in _COMPONENT_PAYMENT_NAMES:
        return 1
    return 0


def _shop_identity(row: Any) -> str:
    explicit = str(getattr(row, "shop_key", "") or "").strip()
    if explicit:
        return explicit
    return "|".join(
        (
            str(getattr(row, "shop", "") or ""),
            str(getattr(row, "grid", "") or ""),
            str(getattr(row, "x", "") or ""),
            str(getattr(row, "y", "") or ""),
        )
    )


def _market_key(row: Any) -> str:
    return "|".join(
        (
            str(int(getattr(row, "item_id", 0) or 0)),
            str(int(getattr(row, "currency_id", 0) or 0)),
            "1" if bool(getattr(row, "item_is_blueprint", False)) else "0",
            "1" if bool(getattr(row, "currency_is_blueprint", False)) else "0",
        )
    )


def _unit_cost(row: Any) -> float:
    quantity = max(1, int(getattr(row, "quantity", 0) or 0))
    cost = max(0, int(getattr(row, "cost", 0) or 0))
    return cost / quantity


def _snapshot_signature(groups: dict[str, list[float]]) -> str:
    payload = [
        (key, [round(value, 6) for value in sorted(values)])
        for key, values in sorted(groups.items())
    ]
    encoded = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_history(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    prices_raw = raw.get("prices")
    prices: dict[str, list[float]] = {}
    if isinstance(prices_raw, dict):
        for key, values in prices_raw.items():
            if not isinstance(values, list):
                continue
            cleaned: list[float] = []
            for value in values[-MAX_HISTORY_SAMPLES:]:
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(number) and number >= 0:
                    cleaned.append(number)
            if cleaned:
                prices[str(key)] = cleaned
    return {
        "version": HISTORY_VERSION,
        "last_signature": str(raw.get("last_signature") or ""),
        "prices": prices,
    }


def _median_absolute_deviation(
    values: Sequence[float],
    median: float,
) -> float:
    if not values:
        return 0.0
    return float(
        statistics.median(
            abs(value - median)
            for value in values
        )
    )


def _confidence(
    peer_count: int,
    history_count: int,
    market_spread: float = 0.0,
) -> str:
    if (
        peer_count >= 4
        or history_count >= 6
        or (peer_count >= 3 and history_count >= 3)
    ):
        level = "High"
    elif peer_count >= 2 or history_count >= 2:
        level = "Medium"
    else:
        level = "Low"

    # Highly scattered markets need more history before they can support an
    # urgent label. A volatile four-shop market is not the same as consensus.
    if market_spread >= 0.90 and history_count < 6:
        return "Medium" if level == "High" else "Low"
    if market_spread >= 0.55 and level == "High" and history_count < 3:
        return "Medium"
    return level


def _benchmark(
    live_peers: Sequence[float],
    historical: Sequence[float],
    unit_cost: float,
) -> tuple[float, str]:
    live_median = (
        float(statistics.median(live_peers))
        if live_peers
        else 0.0
    )
    history_median = (
        float(statistics.median(historical))
        if historical
        else 0.0
    )
    if live_peers and historical:
        live_weight = 0.65 if len(live_peers) >= 2 else 0.45
        return (
            live_median * live_weight
            + history_median * (1.0 - live_weight),
            "blended live-peer and rolling-history median",
        )
    if live_peers:
        return live_median, "live-peer median"
    if historical:
        return history_median, "rolling-history median"
    return unit_cost, "single-listing estimate"


def _progression_gate(
    *,
    numeric_score: float,
    discount: float,
    confidence: str,
    peer_rank: int,
    peer_count: int,
    history_count: int,
    anomaly_score: float,
    item_profile: ItemValueProfile,
    payment_tier: int,
    market_spread: float,
    is_blueprint: bool,
) -> tuple[int, str, str]:
    """Convert relative cheapness into a conservative strategic rating."""
    score = int(round(max(0.0, min(100.0, numeric_score))))
    evidence_count = peer_count + min(history_count, 6)
    top_rank = peer_rank == 1
    medium_evidence = confidence in {"Medium", "High"} and evidence_count >= 3
    strong_evidence = (
        confidence == "High"
        and evidence_count >= 4
    )

    if item_profile.tier == 0:
        score = min(score, 58)
        if discount <= -0.22:
            return min(score, 28), "OVERPRICED", ""
        return score, "FAIR", ""

    if item_profile.tier == 1:
        score = min(score, 74)
        if discount >= 0.18 and confidence != "Low":
            return score, "GOOD VALUE", ""
        if discount <= -0.22:
            return min(score, 28), "OVERPRICED", ""
        return score, "FAIR", ""

    payment_burden = max(0, payment_tier - item_profile.tier)
    blueprint_penalty = 0.10 if is_blueprint else 0.0
    payment_penalty = 0.08 * payment_burden
    volatility_penalty = min(0.12, max(0.0, market_spread - 0.20) * 0.08)
    effective_discount = (
        discount
        - blueprint_penalty
        - payment_penalty
        - volatility_penalty
    )

    if item_profile.category == "component":
        steal_threshold = 0.44
    elif item_profile.category == "rare component":
        steal_threshold = 0.34
    elif item_profile.tier == 2:
        steal_threshold = 0.38
    elif item_profile.tier == 3:
        steal_threshold = 0.25
    else:
        steal_threshold = 0.18

    if item_profile.tier >= 4:
        if (
            effective_discount >= 0.36
            and score >= 91
            and top_rank
            and strong_evidence
            and market_spread < 1.20
        ):
            return score, "CAN'T MISS", "deal"
        if (
            effective_discount >= steal_threshold
            and score >= 82
            and top_rank
            and medium_evidence
        ):
            return max(score, 82), "STEAL", "deal"
    elif item_profile.tier == 3:
        if (
            not is_blueprint
            and effective_discount >= 0.48
            and score >= 93
            and top_rank
            and strong_evidence
            and market_spread < 1.00
        ):
            return score, "CAN'T MISS", "deal"
        if (
            effective_discount >= steal_threshold
            and score >= 84
            and top_rank
            and medium_evidence
        ):
            return max(score, 84), "STEAL", "deal"
    else:
        if (
            effective_discount >= steal_threshold
            and score >= 87
            and top_rank
            and strong_evidence
            and anomaly_score >= 1.0
        ):
            return max(score, 87), "STEAL", "deal"

    good_value_threshold = (
        0.12
        + blueprint_penalty / 2
        + payment_penalty / 2
        + volatility_penalty / 2
    )
    if effective_discount >= good_value_threshold and confidence != "Low":
        return min(score, 79), "GOOD VALUE", ""
    if discount <= -0.22:
        return min(score, 28), "OVERPRICED", ""
    return min(score, 76), "FAIR", ""


def _reason(
    *,
    discount: float,
    benchmark_source: str,
    peer_rank: int,
    peer_count: int,
    history_count: int,
    confidence: str,
    stock: int,
    anomaly_score: float,
    item_profile: ItemValueProfile,
    payment_tier: int,
    label: str,
    market_spread: float,
    is_blueprint: bool,
) -> str:
    if discount > 0.005:
        direction = f"{round(discount * 100):.0f}% below"
    elif discount < -0.005:
        direction = f"{abs(round(discount * 100)):.0f}% above"
    else:
        direction = "near"

    rank_text = (
        f"price rank {peer_rank} of {peer_count} live offers"
        if peer_count > 1
        else "only one live offer"
    )
    progression = (
        f"{item_profile.tier_name.lower()} item"
        + (
            "; urgent-buy eligible"
            if item_profile.actionable
            else "; not treated as an urgent progression purchase"
        )
    )
    payment_text = (
        f"; payment burden tier {payment_tier}"
        if payment_tier > 0
        else ""
    )
    blueprint_text = "; blueprint listing" if is_blueprint else ""
    spread_text = f"; market spread {market_spread:.2f}"
    anomaly_text = (
        f"; robust outlier score {anomaly_score:.1f}"
        if anomaly_score >= 1.5
        else ""
    )
    cap_text = (
        "; relative cheapness is capped below STEAL"
        if item_profile.tier < 2 and label in {"FAIR", "GOOD VALUE"}
        else ""
    )
    return (
        f"{direction} the {benchmark_source}; {rank_text}; "
        f"{history_count} historical sample(s); "
        f"{confidence.lower()} confidence; stock {stock}; "
        f"{progression}{payment_text}{blueprint_text}{spread_text}"
        f"{anomaly_text}{cap_text}."
    )


def score_shop_rows(
    rows: Sequence[Any],
    history: Any = None,
) -> tuple[list[ScoredShopRow], dict[str, Any]]:
    normalized_history = _normalize_history(history)
    previous_prices = {
        key: list(values)
        for key, values in normalized_history["prices"].items()
    }

    current_shop_prices: dict[str, dict[str, float]] = {}
    for row in rows:
        if int(getattr(row, "stock", 0) or 0) <= 0:
            continue
        market = _market_key(row)
        shop = _shop_identity(row)
        unit = _unit_cost(row)
        shops = current_shop_prices.setdefault(market, {})
        shops[shop] = min(unit, shops.get(shop, unit))

    current_groups: dict[str, list[float]] = {
        key: list(shop_prices.values())
        for key, shop_prices in current_shop_prices.items()
    }

    scored: list[ScoredShopRow] = []
    for row in rows:
        key = _market_key(row)
        unit_cost = _unit_cost(row)
        current = list(current_groups.get(key, []))
        historical = list(previous_prices.get(key, []))
        stock = max(
            0,
            int(getattr(row, "stock", 0) or 0),
        )
        item_profile = item_value_profile(
            getattr(row, "item_name", ""),
            getattr(row, "item_id", 0),
        )
        payment_tier = payment_value_tier(
            getattr(row, "currency_name", "")
        )

        own_shop = _shop_identity(row)
        shop_prices = current_shop_prices.get(key, {})
        live_peers = [
            price
            for shop, price in shop_prices.items()
            if shop != own_shop
        ]

        benchmark, benchmark_source = _benchmark(
            live_peers,
            historical,
            unit_cost,
        )
        peer_count = len(current)
        history_count = len(historical)
        discount = (
            (benchmark - unit_cost) / benchmark
            if benchmark > 0
            else 0.0
        )

        ordered_current = sorted(current)
        peer_rank = (
            1
            + sum(
                value < unit_cost - 1e-9
                for value in ordered_current
            )
            if ordered_current
            else 1
        )

        spread_samples = list(live_peers) + historical
        spread_median = (
            float(statistics.median(spread_samples))
            if spread_samples
            else benchmark
        )
        mad = _median_absolute_deviation(
            spread_samples,
            spread_median,
        )
        market_spread = (
            mad / spread_median
            if spread_median > 1e-9
            else 0.0
        )
        confidence = _confidence(
            peer_count,
            history_count,
            market_spread,
        )
        if mad > 1e-9:
            anomaly_score = max(
                0.0,
                (spread_median - unit_cost)
                / (1.4826 * mad),
            )
        else:
            anomaly_score = max(
                0.0,
                discount * 4.0,
            )

        if not spread_samples:
            score = 45
            label = "UNPRICED"
            alert_level = ""
        else:
            numeric_score = 50 + discount * 110
            if confidence == "High":
                numeric_score += 8
            elif confidence == "Medium":
                numeric_score += 4
            if peer_count > 1:
                numeric_score += max(
                    0.0,
                    8.0
                    * (peer_count - peer_rank)
                    / (peer_count - 1),
                )
            if stock > 0:
                numeric_score += min(
                    5.0,
                    math.log2(stock + 1.0),
                )
            score, label, alert_level = _progression_gate(
                numeric_score=numeric_score,
                discount=discount,
                confidence=confidence,
                peer_rank=peer_rank,
                peer_count=peer_count,
                history_count=history_count,
                anomaly_score=anomaly_score,
                item_profile=item_profile,
                payment_tier=payment_tier,
                market_spread=market_spread,
                is_blueprint=bool(
                    getattr(row, "item_is_blueprint", False)
                ),
            )

        if stock <= 0:
            score = min(int(score), 15)
            label = "OUT OF STOCK"
            alert_level = ""

        scored.append(
            ScoredShopRow(
                row=row,
                deal=DealScore(
                    score=int(score),
                    label=label,
                    unit_cost=round(unit_cost, 4),
                    benchmark=round(benchmark, 4),
                    discount_fraction=round(
                        discount,
                        6,
                    ),
                    confidence=confidence,
                    peer_count=peer_count,
                    history_count=history_count,
                    peer_rank=peer_rank,
                    anomaly_score=round(
                        anomaly_score,
                        3,
                    ),
                    reason=_reason(
                        discount=discount,
                        benchmark_source=benchmark_source,
                        peer_rank=peer_rank,
                        peer_count=peer_count,
                        history_count=history_count,
                        confidence=confidence,
                        stock=stock,
                        anomaly_score=anomaly_score,
                        item_profile=item_profile,
                        payment_tier=payment_tier,
                        label=label,
                        market_spread=market_spread,
                        is_blueprint=bool(
                            getattr(row, "item_is_blueprint", False)
                        ),
                    ),
                    alert_level=alert_level,
                    item_tier=item_profile.tier,
                    item_tier_name=item_profile.tier_name,
                    actionable=item_profile.actionable,
                    payment_tier=payment_tier,
                    unique_shop_count=peer_count,
                    market_spread=round(market_spread, 4),
                    blueprint_penalty=bool(
                        getattr(row, "item_is_blueprint", False)
                    ),
                ),
            )
        )

    signature = _snapshot_signature(current_groups)
    updated_prices = {
        key: list(values)
        for key, values in previous_prices.items()
    }
    if (
        signature
        and signature
        != normalized_history["last_signature"]
    ):
        for key, values in current_groups.items():
            updated_prices.setdefault(
                key,
                [],
            ).append(
                float(statistics.median(values))
            )
            updated_prices[key] = updated_prices[
                key
            ][-MAX_HISTORY_SAMPLES:]
        normalized_history["last_signature"] = signature
    normalized_history["prices"] = updated_prices
    normalized_history["version"] = HISTORY_VERSION
    return scored, normalized_history


def sort_scored_rows(
    rows: Iterable[ScoredShopRow],
    mode: str,
) -> list[ScoredShopRow]:
    values = list(rows)
    if mode == "Best value":
        urgency = {
            "CAN'T MISS": 0,
            "STEAL": 1,
            "GOOD VALUE": 2,
            "FAIR": 3,
            "UNPRICED": 4,
            "OVERPRICED": 5,
            "OUT OF STOCK": 6,
        }
        key = lambda item: (
            urgency.get(item.deal.label, 4),
            -item.deal.item_tier,
            -item.deal.score,
            -item.deal.discount_fraction,
            0
            if int(
                getattr(
                    item.row,
                    "stock",
                    0,
                )
                or 0
            )
            > 0
            else 1,
            str(
                getattr(
                    item.row,
                    "item_name",
                    "",
                )
            ).casefold(),
            str(
                getattr(
                    item.row,
                    "shop",
                    "",
                )
            ).casefold(),
        )
    elif mode == "Shop A-Z":
        key = lambda item: (
            str(getattr(item.row, "shop", "")).casefold(),
            str(getattr(item.row, "item_name", "")).casefold(),
            float(getattr(item.row, "cost", 0) or 0),
        )
    elif mode == "Grid":
        key = lambda item: (
            str(getattr(item.row, "grid", "")),
            str(getattr(item.row, "shop", "")).casefold(),
        )
    elif mode == "Lowest cost":
        key = lambda item: (
            item.deal.unit_cost,
            str(getattr(item.row, "item_name", "")).casefold(),
        )
    elif mode == "Highest stock":
        key = lambda item: (
            -int(getattr(item.row, "stock", 0) or 0),
            str(getattr(item.row, "item_name", "")).casefold(),
        )
    else:
        key = lambda item: (
            str(getattr(item.row, "item_name", "")).casefold(),
            item.deal.unit_cost,
            str(getattr(item.row, "shop", "")).casefold(),
        )
    return sorted(values, key=key)
