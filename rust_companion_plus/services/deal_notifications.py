from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


DEAL_ALERT_SEEN_KEY = "marketplace_deal_alerts_seen_v1"
NOTIFICATION_SETTINGS_KEY = "marketplace_notification_settings_v1"
MINIMUM_RATING_OPTIONS = (
    "Steal or better",
    "Can't miss or errors",
    "Possible errors only",
)
DEFAULT_NOTIFICATION_SETTINGS = {
    "enabled": True,
    "minimum_rating": "Steal or better",
    "sound": True,
    "popup_seconds": 15,
    "repeat_hours": 72,
    "max_alerts": 3,
}
ALERT_LABELS = {
    "POSSIBLE LISTING ERROR",
    "CAN'T MISS",
    "STEAL",
}


@dataclass(frozen=True, slots=True)
class DealAlert:
    fingerprint: str
    severity: int
    title: str
    message: str
    label: str
    score: int
    grid: str
    shop: str
    item_name: str


def _bounded_int(
    value: Any,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def normalize_notification_settings(raw: Any) -> dict[str, Any]:
    source = dict(raw) if isinstance(raw, dict) else {}
    minimum_rating = str(
        source.get(
            "minimum_rating",
            DEFAULT_NOTIFICATION_SETTINGS["minimum_rating"],
        )
    )
    if minimum_rating not in MINIMUM_RATING_OPTIONS:
        minimum_rating = DEFAULT_NOTIFICATION_SETTINGS["minimum_rating"]
    return {
        "enabled": bool(
            source.get(
                "enabled",
                DEFAULT_NOTIFICATION_SETTINGS["enabled"],
            )
        ),
        "minimum_rating": minimum_rating,
        "sound": bool(
            source.get(
                "sound",
                DEFAULT_NOTIFICATION_SETTINGS["sound"],
            )
        ),
        "popup_seconds": _bounded_int(
            source.get("popup_seconds"),
            DEFAULT_NOTIFICATION_SETTINGS["popup_seconds"],
            5,
            60,
        ),
        "repeat_hours": _bounded_int(
            source.get("repeat_hours"),
            DEFAULT_NOTIFICATION_SETTINGS["repeat_hours"],
            1,
            720,
        ),
        "max_alerts": _bounded_int(
            source.get("max_alerts"),
            DEFAULT_NOTIFICATION_SETTINGS["max_alerts"],
            1,
            10,
        ),
    }


def save_notification_settings(
    store: Any,
    raw: Any,
) -> dict[str, Any]:
    settings = normalize_notification_settings(raw)
    store.set(NOTIFICATION_SETTINGS_KEY, settings)
    return settings


def clear_deal_alert_history(store: Any) -> None:
    store.set(DEAL_ALERT_SEEN_KEY, {})


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_seen(
    raw: Any,
    now: datetime,
    repeat_hours: int,
) -> dict[str, str]:
    source = raw.get("seen") if isinstance(raw, dict) else {}
    if not isinstance(source, dict):
        source = {}
    cutoff = now - timedelta(hours=max(1, int(repeat_hours)))
    result: dict[str, str] = {}
    for key, value in source.items():
        parsed = _parse_time(value)
        if parsed is not None and parsed >= cutoff:
            result[str(key)] = parsed.isoformat(timespec="seconds")
    return result


def listing_fingerprint(scored: Any, profile_key: str) -> str:
    row = scored.row
    deal = scored.deal
    fields = (
        profile_key or "unknown-server",
        getattr(row, "shop_key", ""),
        getattr(row, "grid", ""),
        getattr(row, "item_id", 0),
        getattr(row, "currency_id", 0),
        getattr(row, "quantity", 0),
        getattr(row, "cost", 0),
        getattr(row, "stock", 0),
        bool(getattr(row, "item_is_blueprint", False)),
        bool(getattr(row, "currency_is_blueprint", False)),
        deal.label,
    )
    return hashlib.sha256(
        "|".join(str(value) for value in fields).encode("utf-8")
    ).hexdigest()


def _eligible(scored: Any, settings: dict[str, Any]) -> bool:
    row = scored.row
    deal = scored.deal
    label = str(deal.label)
    if int(getattr(row, "stock", 0) or 0) <= 0:
        return False
    if label not in ALERT_LABELS or str(deal.confidence) == "Low":
        return False

    minimum = settings["minimum_rating"]
    if minimum == "Possible errors only":
        return label == "POSSIBLE LISTING ERROR"
    if minimum == "Can't miss or errors":
        return label in {
            "POSSIBLE LISTING ERROR",
            "CAN'T MISS",
        }
    return label in ALERT_LABELS and not (
        label == "STEAL" and int(deal.score) < 80
    )


def _alert(scored: Any, fingerprint: str) -> DealAlert:
    row = scored.row
    deal = scored.deal
    label = str(deal.label)
    severity = (
        3
        if label == "POSSIBLE LISTING ERROR"
        else 2
        if label == "CAN'T MISS"
        else 1
    )
    item_name = str(getattr(row, "item_name", "Item") or "Item")
    shop = str(getattr(row, "shop", "Shop") or "Shop")
    grid = str(getattr(row, "grid", "?") or "?")
    quantity = int(getattr(row, "quantity", 0) or 0)
    cost = int(getattr(row, "cost", 0) or 0)
    currency = str(
        getattr(row, "currency_name", "payment") or "payment"
    )
    title = (
        f"Possible listing error: {item_name}"
        if label == "POSSIBLE LISTING ERROR"
        else f"{label.title()}: {item_name}"
    )
    message = (
        f"{shop} at {grid}: {quantity} x {item_name} for "
        f"{cost} x {currency}. {deal.reason}"
    )
    return DealAlert(
        fingerprint=fingerprint,
        severity=severity,
        title=title,
        message=message,
        label=label,
        score=int(deal.score),
        grid=grid,
        shop=shop,
        item_name=item_name,
    )


def collect_deal_alerts(
    scored_rows: Iterable[Any],
    seen_state: Any,
    *,
    profile_key: str,
    settings: Any = None,
    now: datetime | None = None,
    max_alerts: int | None = None,
) -> tuple[list[DealAlert], dict[str, Any]]:
    configured = normalize_notification_settings(settings)
    current = _now(now)
    seen = _normalized_seen(
        seen_state,
        current,
        configured["repeat_hours"],
    )
    if not configured["enabled"]:
        return (
            [],
            {
                "version": 1,
                "updated_at": current.isoformat(timespec="seconds"),
                "seen": seen,
            },
        )

    candidates: list[DealAlert] = []
    for scored in scored_rows:
        if not _eligible(scored, configured):
            continue
        fingerprint = listing_fingerprint(scored, profile_key)
        if fingerprint not in seen:
            candidates.append(_alert(scored, fingerprint))
        seen[fingerprint] = current.isoformat(timespec="seconds")

    candidates.sort(
        key=lambda alert: (
            -alert.severity,
            -alert.score,
            alert.item_name.casefold(),
            alert.shop.casefold(),
        )
    )
    limit = (
        configured["max_alerts"]
        if max_alerts is None
        else _bounded_int(max_alerts, configured["max_alerts"], 1, 10)
    )
    return (
        candidates[:limit],
        {
            "version": 1,
            "updated_at": current.isoformat(timespec="seconds"),
            "seen": seen,
        },
    )
