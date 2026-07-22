from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable


SMART_SYSTEMS_KEY = "smart_device_systems_v1"
SMART_SCENES_KEY = "smart_device_scenes_v1"
SMART_RULES_KEY = "smart_device_rules_v1"
SMART_ACTIVITY_KEY = "smart_device_activity_v1"
SMART_SETTINGS_KEY = "smart_device_settings_v1"

RULE_CONDITIONS = (
    "Value turns ON",
    "Value turns OFF",
    "Capacity below",
    "Status changes",
    "Entity error",
)
RULE_ACTIONS = (
    "Notify only",
    "Run scene",
    "Notify and run scene",
)
DEFAULT_SMART_SETTINGS = {
    "auto_refresh": True,
    "refresh_seconds": 5,
    "rules_armed": False,
    "verify_scene": True,
    "max_activity": 200,
}


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


def normalize_smart_settings(raw: Any) -> dict[str, Any]:
    source = dict(raw) if isinstance(raw, dict) else {}
    return {
        "auto_refresh": bool(source.get("auto_refresh", True)),
        "refresh_seconds": _bounded_int(
            source.get("refresh_seconds"),
            5,
            3,
            120,
        ),
        "rules_armed": bool(source.get("rules_armed", False)),
        "verify_scene": bool(source.get("verify_scene", True)),
        "max_activity": _bounded_int(
            source.get("max_activity"),
            200,
            20,
            1000,
        ),
    }


def _clean_device_ids(
    values: Iterable[Any],
    valid_ids: set[int] | None = None,
) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for raw in values:
        try:
            entity_id = int(raw)
        except (TypeError, ValueError):
            continue
        if entity_id <= 0 or entity_id in seen:
            continue
        if valid_ids is not None and entity_id not in valid_ids:
            continue
        seen.add(entity_id)
        result.append(entity_id)
    return result


def normalize_systems(
    raw: Any,
    device_ids: Iterable[Any] = (),
) -> list[dict[str, Any]]:
    valid = set(_clean_device_ids(device_ids))
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, value in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(value, dict):
            continue
        name = str(value.get("name") or "").strip()
        if not name:
            continue
        system_id = str(
            value.get("id")
            or hashlib.sha1(
                f"{name}:{index}".encode("utf-8")
            ).hexdigest()[:12]
        )
        if system_id in seen:
            continue
        members = _clean_device_ids(
            value.get("device_ids") or [],
            valid or None,
        )
        if not members:
            continue
        seen.add(system_id)
        result.append(
            {
                "id": system_id,
                "name": name,
                "zone": str(value.get("zone") or "Main Base"),
                "purpose": str(value.get("purpose") or "General"),
                "critical": bool(value.get("critical", False)),
                "device_ids": members,
            }
        )
    result.sort(
        key=lambda row: (
            not bool(row.get("critical")),
            str(row.get("zone", "")).casefold(),
            str(row.get("name", "")).casefold(),
        )
    )
    return result


def normalize_scenes(
    raw: Any,
    device_ids: Iterable[Any] = (),
) -> list[dict[str, Any]]:
    valid = set(_clean_device_ids(device_ids))
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, value in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(value, dict):
            continue
        name = str(value.get("name") or "").strip()
        if not name:
            continue
        scene_id = str(
            value.get("id")
            or hashlib.sha1(
                f"{name}:{index}".encode("utf-8")
            ).hexdigest()[:12]
        )
        if scene_id in seen:
            continue
        actions: list[dict[str, Any]] = []
        action_ids: set[int] = set()
        for action in value.get("actions") or []:
            if not isinstance(action, dict):
                continue
            try:
                entity_id = int(action.get("entity_id") or 0)
            except (TypeError, ValueError):
                continue
            if entity_id <= 0 or entity_id in action_ids:
                continue
            if valid and entity_id not in valid:
                continue
            action_ids.add(entity_id)
            actions.append(
                {
                    "entity_id": entity_id,
                    "value": bool(action.get("value", False)),
                }
            )
        if not actions:
            continue
        seen.add(scene_id)
        result.append(
            {
                "id": scene_id,
                "name": name,
                "description": str(value.get("description") or ""),
                "actions": actions,
                "verify": bool(value.get("verify", True)),
                "confirm": bool(value.get("confirm", True)),
                "favorite": bool(value.get("favorite", False)),
            }
        )
    result.sort(
        key=lambda row: (
            not bool(row.get("favorite")),
            str(row.get("name", "")).casefold(),
        )
    )
    return result


def normalize_rules(
    raw: Any,
    device_ids: Iterable[Any] = (),
    scene_ids: Iterable[Any] = (),
) -> list[dict[str, Any]]:
    valid_devices = set(_clean_device_ids(device_ids))
    valid_scenes = {str(value) for value in scene_ids if str(value)}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, value in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(value, dict):
            continue
        try:
            source_id = int(value.get("source_entity_id") or 0)
        except (TypeError, ValueError):
            continue
        if source_id <= 0 or (
            valid_devices and source_id not in valid_devices
        ):
            continue
        condition = str(value.get("condition") or RULE_CONDITIONS[0])
        if condition not in RULE_CONDITIONS:
            condition = RULE_CONDITIONS[0]
        action = str(value.get("action") or RULE_ACTIONS[0])
        if action not in RULE_ACTIONS:
            action = RULE_ACTIONS[0]
        scene_id = str(value.get("scene_id") or "")
        if (
            action in {"Run scene", "Notify and run scene"}
            and scene_id not in valid_scenes
        ):
            action = "Notify only"
            scene_id = ""
        name = str(value.get("name") or "").strip()
        if not name:
            name = f"{condition} on {source_id}"
        rule_id = str(
            value.get("id")
            or hashlib.sha1(
                f"{name}:{source_id}:{index}".encode("utf-8")
            ).hexdigest()[:12]
        )
        if rule_id in seen:
            continue
        seen.add(rule_id)
        result.append(
            {
                "id": rule_id,
                "name": name,
                "source_entity_id": source_id,
                "condition": condition,
                "threshold": _bounded_int(
                    value.get("threshold"),
                    25,
                    0,
                    1000000,
                ),
                "action": action,
                "scene_id": scene_id,
                "cooldown_seconds": _bounded_int(
                    value.get("cooldown_seconds"),
                    60,
                    5,
                    86400,
                ),
                "enabled": bool(value.get("enabled", True)),
                "last_triggered_at": str(
                    value.get("last_triggered_at") or ""
                ),
            }
        )
    result.sort(
        key=lambda row: (
            not bool(row.get("enabled")),
            str(row.get("name", "")).casefold(),
        )
    )
    return result


def status_value(status: Any) -> bool | None:
    if not isinstance(status, dict) or status.get("error"):
        return None
    value = status.get("value")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"on", "true", "1", "active", "open"}:
            return True
        if lowered in {"off", "false", "0", "inactive", "closed"}:
            return False
    return None


def status_capacity(status: Any) -> float | None:
    if not isinstance(status, dict) or status.get("error"):
        return None
    value = status.get("capacity")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def scene_plan(
    scene: dict[str, Any],
    statuses: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    current = statuses or {}
    plan: list[dict[str, Any]] = []
    for action in scene.get("actions") or []:
        try:
            entity_id = int(action.get("entity_id") or 0)
        except (TypeError, ValueError):
            continue
        desired = bool(action.get("value", False))
        existing = status_value(current.get(entity_id, {}))
        plan.append(
            {
                "entity_id": entity_id,
                "value": desired,
                "already_set": existing is desired,
            }
        )
    return plan


def system_summary(
    system: dict[str, Any],
    statuses: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    members = _clean_device_ids(system.get("device_ids") or [])
    online = 0
    on = 0
    errors = 0
    capacities: list[float] = []
    for entity_id in members:
        status = statuses.get(entity_id, {})
        if status.get("error"):
            errors += 1
            continue
        if status:
            online += 1
        if status_value(status) is True:
            on += 1
        capacity = status_capacity(status)
        if capacity is not None:
            capacities.append(capacity)
    return {
        "count": len(members),
        "online": online,
        "on": on,
        "errors": errors,
        "minimum_capacity": min(capacities) if capacities else None,
    }


def _parse_iso(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def evaluate_rules(
    rules: list[dict[str, Any]],
    statuses: dict[int, dict[str, Any]],
    previous_statuses: dict[int, dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    previous = previous_statuses or {}
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    triggered: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []

    for original in rules:
        rule = dict(original)
        if not bool(rule.get("enabled", True)):
            updated.append(rule)
            continue
        entity_id = int(rule.get("source_entity_id") or 0)
        status = statuses.get(entity_id, {})
        old_status = previous.get(entity_id, {})
        condition = str(rule.get("condition") or "")
        matched = False

        if condition == "Value turns ON":
            matched = (
                status_value(status) is True
                and status_value(old_status) is not True
            )
        elif condition == "Value turns OFF":
            matched = (
                status_value(status) is False
                and status_value(old_status) is not False
            )
        elif condition == "Capacity below":
            capacity = status_capacity(status)
            matched = (
                capacity is not None
                and capacity < float(rule.get("threshold", 0) or 0)
            )
        elif condition == "Status changes":
            matched = bool(old_status) and status != old_status
        elif condition == "Entity error":
            matched = bool(status.get("error"))

        last = _parse_iso(rule.get("last_triggered_at"))
        cooldown = max(5, int(rule.get("cooldown_seconds", 60) or 60))
        if matched and last is not None:
            matched = (
                current_time - last
            ).total_seconds() >= cooldown

        if matched:
            rule["last_triggered_at"] = current_time.isoformat(
                timespec="seconds"
            )
            triggered.append(dict(rule))
        updated.append(rule)

    return triggered, updated


def append_activity(
    rows: Any,
    message: str,
    *,
    level: str = "info",
    limit: int = 200,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    result = [
        dict(value)
        for value in rows
        if isinstance(value, dict)
    ] if isinstance(rows, list) else []
    current = now or datetime.now().astimezone()
    result.append(
        {
            "time": current.isoformat(timespec="seconds"),
            "level": str(level or "info"),
            "message": str(message or ""),
        }
    )
    return result[-max(20, int(limit)):]
