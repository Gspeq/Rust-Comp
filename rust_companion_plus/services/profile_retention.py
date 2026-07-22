from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from rust_companion_plus.services.server_profiles import (
    PROFILE_ROOT,
    PROFILE_STORE_KEY,
    _safe_profile_folder_name,
)


PROFILE_RETENTION_DAYS = 30
PROFILE_CLEANUP_STATE_KEY = "saved_server_profile_cleanup"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_profile_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def profile_activity_time(record: dict[str, Any]) -> datetime | None:
    for key in ("live_updated_at", "saved_at"):
        parsed = parse_profile_time(record.get(key))
        if parsed is not None:
            return parsed
    return None


def _mapping(store: Any, key: str) -> dict[str, Any]:
    raw = store.get(key, {}) or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _remove_profile_assets(
    key: str,
    record: dict[str, Any],
    *,
    asset_root: Path,
) -> None:
    candidates: set[Path] = {
        Path(asset_root) / _safe_profile_folder_name(key),
    }
    assets = record.get("assets")
    if isinstance(assets, dict):
        for name in (
            "map_image_path",
            "parsed_map_dir",
            "raw_map_path",
        ):
            raw = str(assets.get(name) or "").strip()
            if not raw:
                continue
            path = Path(raw).expanduser().resolve(strict=False)
            root = Path(asset_root).expanduser().resolve(strict=False)
            try:
                path.relative_to(root)
            except ValueError:
                continue
            candidates.add(path if path.is_dir() else path.parent)

    for candidate in sorted(candidates, key=lambda path: len(path.parts), reverse=True):
        try:
            if candidate.is_dir():
                shutil.rmtree(candidate)
            elif candidate.exists():
                candidate.unlink()
        except OSError:
            # Profile metadata must still be removable if a cached file is locked.
            continue


def delete_saved_profile(
    store: Any,
    key: str,
    *,
    asset_root: Path = PROFILE_ROOT,
) -> bool:
    key = str(key or "").strip()
    if not key:
        return False

    profiles = _mapping(store, PROFILE_STORE_KEY)
    record = profiles.pop(key, None)
    if not isinstance(record, dict):
        return False

    store.set(PROFILE_STORE_KEY, profiles)

    for mapping_key in (
        "credential_profiles",
        "credential_profile_metadata",
    ):
        values = _mapping(store, mapping_key)
        if key in values:
            values.pop(key, None)
            store.set(mapping_key, values)

    active = str(store.get("active_server_profile_key", "") or "").strip()
    if active == key:
        store.set("active_server_profile_key", "")

    _remove_profile_assets(key, record, asset_root=Path(asset_root))
    return True


def delete_all_saved_profiles(
    store: Any,
    *,
    asset_root: Path = PROFILE_ROOT,
) -> list[str]:
    profiles = _mapping(store, PROFILE_STORE_KEY)
    removed: list[str] = []
    for key in list(profiles):
        if delete_saved_profile(store, key, asset_root=asset_root):
            removed.append(key)
    return removed


def purge_expired_profiles(
    store: Any,
    *,
    max_age_days: int = PROFILE_RETENTION_DAYS,
    now: datetime | None = None,
    asset_root: Path = PROFILE_ROOT,
) -> list[str]:
    effective_now = now or _utc_now()
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=timezone.utc)
    effective_now = effective_now.astimezone(timezone.utc)
    cutoff = effective_now - timedelta(days=max(1, int(max_age_days)))

    profiles = _mapping(store, PROFILE_STORE_KEY)
    expired: list[str] = []
    for key, raw in profiles.items():
        if not isinstance(raw, dict):
            continue
        activity = profile_activity_time(raw)
        if activity is not None and activity < cutoff:
            expired.append(str(key))

    removed: list[str] = []
    for key in expired:
        if delete_saved_profile(store, key, asset_root=asset_root):
            removed.append(key)

    store.set(
        PROFILE_CLEANUP_STATE_KEY,
        {
            "checked_at": effective_now.isoformat(timespec="seconds"),
            "retention_days": max(1, int(max_age_days)),
            "removed": removed,
        },
    )
    return removed
