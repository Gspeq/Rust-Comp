from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


DEAL_ALERT_SEEN_KEY = "marketplace_deal_alerts_seen_v1"
NOTIFICATION_SETTINGS_KEY = "marketplace_notification_settings_v1"
MINIMUM_RATING_OPTIONS = (
    "Good value or better",
    "Steal or better",
    "Can't miss or errors",
    "Possible errors only",
)
LOOT_PRESETS = (
    "All loot",
    "Basic loot",
    "Mid tier loot",
    "High tier loot",
    "Endgame loot",
    "Custom items only",
)

# These are intentionally readable search terms rather than item IDs. The item
# catalog already normalizes Rust+ IDs to display names, and partial matching
# also covers common variants such as doors, ammunition, and blueprints.
LOOT_PRESET_TERMS: dict[str, tuple[str, ...]] = {
    "All loot": (),
    "Basic loot": (
        "wood",
        "stone",
        "metal fragments",
        "cloth",
        "leather",
        "low grade fuel",
        "scrap",
        "rope",
        "sewing kit",
        "road signs",
        "metal pipe",
        "gears",
        "sheet metal",
        "hatchet",
        "pickaxe",
        "crossbow",
        "nailgun",
        "revolver",
        "double barrel",
    ),
    "Mid tier loot": (
        "semi-automatic pistol",
        "python revolver",
        "pump shotgun",
        "semi-automatic rifle",
        "thompson",
        "custom smg",
        "hazmat suit",
        "medical syringe",
        "garage door",
        "satchel charge",
        "bean can grenade",
        "rifle body",
        "smg body",
        "tech trash",
        "targeting computer",
        "cctv camera",
        "large battery",
        "wind turbine",
    ),
    "High tier loot": (
        "assault rifle",
        "mp5a4",
        "lr-300",
        "bolt action rifle",
        "l96 rifle",
        "rocket launcher",
        "rocket",
        "timed explosive charge",
        "explosive 5.56",
        "armored door",
        "metal facemask",
        "metal chest plate",
        "high quality metal",
        "auto turret",
        "sam site",
    ),
    "Endgame loot": (
        "timed explosive charge",
        "rocket",
        "rocket launcher",
        "explosive 5.56",
        "m249",
        "l96 rifle",
        "lr-300",
        "assault rifle",
        "mp5a4",
        "bolt action rifle",
        "armored door",
        "armored double door",
        "metal facemask",
        "metal chest plate",
        "supply signal",
        "multiple grenade launcher",
        "high velocity rocket",
        "incendiary rocket",
    ),
    "Custom items only": (),
}

DEFAULT_NOTIFICATION_SETTINGS = {
    "enabled": True,
    "minimum_rating": "Steal or better",
    "loot_preset": "All loot",
    "specific_items": [],
    "specific_item_any_listing": False,
    "include_blueprints": True,
    "minimum_stock": 1,
    "maximum_cost": 0,
    "sound": True,
    "popup_seconds": 15,
    "repeat_hours": 72,
    "max_alerts": 3,
    "windows_notifications": True,
    "in_app_notifications": True,
}
ALERT_LABELS = {
    "POSSIBLE LISTING ERROR",
    "CAN'T MISS",
    "STEAL",
    "GOOD VALUE",
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


def normalize_specific_items(raw: Any) -> list[str]:
    if isinstance(raw, str):
        values = raw.replace("\n", ",").split(",")
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").strip().casefold().split())
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text[:80])
    return result[:100]


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

    preset = str(
        source.get(
            "loot_preset",
            DEFAULT_NOTIFICATION_SETTINGS["loot_preset"],
        )
    )
    if preset not in LOOT_PRESETS:
        preset = DEFAULT_NOTIFICATION_SETTINGS["loot_preset"]

    return {
        "enabled": bool(
            source.get(
                "enabled",
                DEFAULT_NOTIFICATION_SETTINGS["enabled"],
            )
        ),
        "minimum_rating": minimum_rating,
        "loot_preset": preset,
        "specific_items": normalize_specific_items(
            source.get("specific_items", [])
        ),
        "specific_item_any_listing": bool(
            source.get(
                "specific_item_any_listing",
                DEFAULT_NOTIFICATION_SETTINGS[
                    "specific_item_any_listing"
                ],
            )
        ),
        "include_blueprints": bool(
            source.get(
                "include_blueprints",
                DEFAULT_NOTIFICATION_SETTINGS["include_blueprints"],
            )
        ),
        "minimum_stock": _bounded_int(
            source.get("minimum_stock"),
            DEFAULT_NOTIFICATION_SETTINGS["minimum_stock"],
            0,
            1000000,
        ),
        "maximum_cost": _bounded_int(
            source.get("maximum_cost"),
            DEFAULT_NOTIFICATION_SETTINGS["maximum_cost"],
            0,
            1000000000,
        ),
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
        "windows_notifications": bool(
            source.get(
                "windows_notifications",
                DEFAULT_NOTIFICATION_SETTINGS[
                    "windows_notifications"
                ],
            )
        ),
        "in_app_notifications": bool(
            source.get(
                "in_app_notifications",
                DEFAULT_NOTIFICATION_SETTINGS["in_app_notifications"],
            )
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


def _item_text(scored: Any) -> str:
    row = scored.row
    return " ".join(
        (
            str(getattr(row, "item_name", "") or ""),
            str(getattr(row, "item_id", "") or ""),
        )
    ).casefold()


def _specific_match(scored: Any, settings: dict[str, Any]) -> bool:
    text = _item_text(scored)
    return any(term in text for term in settings["specific_items"])


def _preset_match(scored: Any, settings: dict[str, Any]) -> bool:
    preset = settings["loot_preset"]
    specific = _specific_match(scored, settings)
    if preset == "Custom items only":
        return specific
    terms = LOOT_PRESET_TERMS.get(preset, ())
    if not terms:
        return True
    text = _item_text(scored)
    return specific or any(term in text for term in terms)


def _rating_eligible(label: str, score: int, minimum: str) -> bool:
    if minimum == "Possible errors only":
        return label == "POSSIBLE LISTING ERROR"
    if minimum == "Can't miss or errors":
        return label in {
            "POSSIBLE LISTING ERROR",
            "CAN'T MISS",
        }
    if minimum == "Steal or better":
        return label in {
            "POSSIBLE LISTING ERROR",
            "CAN'T MISS",
            "STEAL",
        } and not (label == "STEAL" and score < 80)
    return label in ALERT_LABELS


def _eligible(
    scored: Any,
    settings: dict[str, Any],
) -> tuple[bool, bool]:
    row = scored.row
    deal = scored.deal
    stock = int(getattr(row, "stock", 0) or 0)
    cost = int(getattr(row, "cost", 0) or 0)
    if stock <= 0 or stock < settings["minimum_stock"]:
        return False, False
    if settings["maximum_cost"] and cost > settings["maximum_cost"]:
        return False, False
    if (
        not settings["include_blueprints"]
        and (
            bool(getattr(row, "item_is_blueprint", False))
            or bool(getattr(row, "currency_is_blueprint", False))
        )
    ):
        return False, False
    if not _preset_match(scored, settings):
        return False, False

    specific = _specific_match(scored, settings)
    if specific and settings["specific_item_any_listing"]:
        return True, True

    label = str(deal.label)
    if str(deal.confidence) == "Low":
        return False, False
    return (
        _rating_eligible(
            label,
            int(deal.score),
            settings["minimum_rating"],
        ),
        False,
    )


def _alert(
    scored: Any,
    fingerprint: str,
    *,
    watched_item: bool,
) -> DealAlert:
    row = scored.row
    deal = scored.deal
    label = "WATCHED ITEM" if watched_item else str(deal.label)
    severity = (
        3
        if str(deal.label) == "POSSIBLE LISTING ERROR"
        else 2
        if str(deal.label) == "CAN'T MISS"
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
    if watched_item:
        title = f"Watched item listed: {item_name}"
    elif str(deal.label) == "POSSIBLE LISTING ERROR":
        title = f"Possible listing error: {item_name}"
    else:
        title = f"{str(deal.label).title()}: {item_name}"
    reason = str(getattr(deal, "reason", "") or "")
    message = (
        f"{shop} at {grid}: {quantity} x {item_name} for "
        f"{cost} x {currency}. {reason}"
    ).strip()
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
                "version": 2,
                "updated_at": current.isoformat(timespec="seconds"),
                "seen": seen,
            },
        )

    candidates: list[DealAlert] = []
    for scored in scored_rows:
        eligible, watched_item = _eligible(scored, configured)
        if not eligible:
            continue
        fingerprint = listing_fingerprint(scored, profile_key)
        if watched_item:
            fingerprint = hashlib.sha256(
                f"watched:{fingerprint}".encode("utf-8")
            ).hexdigest()
        if fingerprint not in seen:
            candidates.append(
                _alert(
                    scored,
                    fingerprint,
                    watched_item=watched_item,
                )
            )
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
        else _bounded_int(
            max_alerts,
            configured["max_alerts"],
            1,
            10,
        )
    )
    return (
        candidates[:limit],
        {
            "version": 2,
            "updated_at": current.isoformat(timespec="seconds"),
            "seen": seen,
        },
    )
