from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


HISTORY_VERSION = 1
MAX_HISTORY_SAMPLES = 96


@dataclass(frozen=True, slots=True)
class DealScore:
    score: int
    label: str
    unit_cost: float
    benchmark: float
    discount_fraction: float
    confidence: str

    @property
    def discount_percent(self) -> int:
        return int(round(self.discount_fraction * 100))


@dataclass(frozen=True, slots=True)
class ScoredShopRow:
    row: Any
    deal: DealScore


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
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
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
                if number >= 0:
                    cleaned.append(number)
            if cleaned:
                prices[str(key)] = cleaned
    return {
        "version": HISTORY_VERSION,
        "last_signature": str(raw.get("last_signature") or ""),
        "prices": prices,
    }


def score_shop_rows(
    rows: Sequence[Any],
    history: Any = None,
) -> tuple[list[ScoredShopRow], dict[str, Any]]:
    normalized_history = _normalize_history(history)
    current_groups: dict[str, list[float]] = {}
    for row in rows:
        if int(getattr(row, "stock", 0) or 0) <= 0:
            continue
        current_groups.setdefault(_market_key(row), []).append(_unit_cost(row))

    signature = _snapshot_signature(current_groups)
    prices = {
        key: list(values)
        for key, values in normalized_history["prices"].items()
    }
    if signature and signature != normalized_history["last_signature"]:
        for key, values in current_groups.items():
            prices.setdefault(key, []).append(float(statistics.median(values)))
            prices[key] = prices[key][-MAX_HISTORY_SAMPLES:]
        normalized_history["last_signature"] = signature
    normalized_history["prices"] = prices

    scored: list[ScoredShopRow] = []
    for row in rows:
        key = _market_key(row)
        unit_cost = _unit_cost(row)
        current = list(current_groups.get(key, []))
        historical = list(prices.get(key, []))

        benchmark_samples = current + historical
        if benchmark_samples:
            benchmark = float(statistics.median(benchmark_samples))
        else:
            benchmark = unit_cost

        peer_count = len(current)
        history_count = len(historical)
        if peer_count >= 3 or history_count >= 4:
            confidence = "High"
        elif peer_count >= 2 or history_count >= 1:
            confidence = "Medium"
        else:
            confidence = "Low"

        if benchmark <= 0:
            discount = 0.0
        else:
            discount = (benchmark - unit_cost) / benchmark

        stock = max(0, int(getattr(row, "stock", 0) or 0))
        if not benchmark_samples:
            score = 50
            label = "UNPRICED"
        else:
            # Center fair value around 50, then let a 50% discount approach 100.
            score = int(round(50 + discount * 100))
            score += min(6, stock // 8) if stock else 0
            score = max(0, min(100, score))
            if confidence != "Low" and score >= 90 and discount >= 0.30:
                label = "CAN'T MISS"
            elif score >= 78 and discount >= 0.16:
                label = "STEAL"
            elif score >= 64 and discount >= 0.07:
                label = "GOOD VALUE"
            elif score <= 28 and discount <= -0.22:
                label = "OVERPRICED"
            else:
                label = "FAIR"

        if stock <= 0:
            score = min(score, 15)
            label = "OUT OF STOCK"

        scored.append(
            ScoredShopRow(
                row=row,
                deal=DealScore(
                    score=score,
                    label=label,
                    unit_cost=round(unit_cost, 4),
                    benchmark=round(benchmark, 4),
                    discount_fraction=round(discount, 6),
                    confidence=confidence,
                ),
            )
        )

    return scored, normalized_history


def sort_scored_rows(
    rows: Iterable[ScoredShopRow],
    mode: str,
) -> list[ScoredShopRow]:
    values = list(rows)
    if mode == "Best value":
        key = lambda item: (
            -item.deal.score,
            -item.deal.discount_fraction,
            0 if int(getattr(item.row, "stock", 0) or 0) > 0 else 1,
            str(getattr(item.row, "item_name", "")).casefold(),
            str(getattr(item.row, "shop", "")).casefold(),
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
