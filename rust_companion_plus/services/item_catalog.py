from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from rust_companion_plus.config import APP_DATA_DIR


CATALOG_URL = "https://api.carbonmod.gg/meta/rust/items.json"
CACHE_PATH = APP_DATA_DIR / "rust-item-catalog.json"
CACHE_MAX_AGE = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class RustItemEntry:
    item_id: int
    name: str
    shortname: str = ""

    @property
    def search_text(self) -> str:
        return f"{self.name} {self.shortname} {self.item_id}".casefold()


class RustItemCatalog:
    def __init__(
        self,
        *,
        cache_path: Path = CACHE_PATH,
        catalog_url: str = CATALOG_URL,
        fetch_json: Callable[[str], Any] | None = None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.catalog_url = catalog_url
        self._fetch_json = fetch_json or _download_json
        self.entries: dict[int, RustItemEntry] = {}
        self.loaded_from = ""
        self.last_error = ""
        self.loaded_at = ""

    def load(self, *, force: bool = False) -> int:
        cached_payload = self._read_cache()
        cache_is_fresh = (
            cached_payload is not None
            and not force
            and self._cache_is_fresh(cached_payload)
        )

        if cache_is_fresh:
            self.entries = _parse_cached_entries(cached_payload)
            self.loaded_from = "cache"
            self.loaded_at = str(cached_payload.get("fetched_at") or "")
            return len(self.entries)

        try:
            payload = self._fetch_json(self.catalog_url)
            entries = parse_item_catalog(payload)
            if not entries:
                raise ValueError("The item catalog contained no usable item definitions.")
        except Exception as exc:
            self.last_error = str(exc)
            if cached_payload is not None:
                self.entries = _parse_cached_entries(cached_payload)
                self.loaded_from = "stale cache"
                self.loaded_at = str(cached_payload.get("fetched_at") or "")
                return len(self.entries)
            self.entries = {}
            self.loaded_from = "IDs only"
            self.loaded_at = ""
            return 0

        self.entries = entries
        self.loaded_from = "network"
        self.loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.last_error = ""
        self._write_cache()
        return len(self.entries)

    def refresh(self) -> int:
        return self.load(force=True)

    def label(self, item_id: Any) -> str:
        numeric = _coerce_int(item_id)
        if numeric is None:
            return "Unknown item"
        entry = self.entries.get(numeric)
        return entry.name if entry is not None else f"Item {numeric}"

    def shortname(self, item_id: Any) -> str:
        numeric = _coerce_int(item_id)
        if numeric is None:
            return ""
        entry = self.entries.get(numeric)
        return entry.shortname if entry is not None else ""

    def search_text(self, item_id: Any) -> str:
        numeric = _coerce_int(item_id)
        if numeric is None:
            return str(item_id or "").casefold()
        entry = self.entries.get(numeric)
        if entry is not None:
            return entry.search_text
        return f"item {numeric} {numeric}".casefold()

    def description(self) -> str:
        if self.entries:
            return f"{len(self.entries)} item names from {self.loaded_from}"
        if self.last_error:
            return "item-name catalog unavailable; searching IDs"
        return "item names loading"

    def _read_cache(self) -> dict[str, Any] | None:
        if not self.cache_path.is_file():
            return None
        try:
            payload = json.loads(
                self.cache_path.read_text(encoding="utf-8-sig")
            )
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _cache_is_fresh(self, payload: dict[str, Any]) -> bool:
        raw = str(payload.get("fetched_at") or "")
        if not raw:
            return False
        try:
            fetched = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return False
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - fetched <= CACHE_MAX_AGE

    def _write_cache(self) -> None:
        payload = {
            "source": self.catalog_url,
            "fetched_at": self.loaded_at,
            "items": {
                str(item_id): {
                    "name": entry.name,
                    "shortname": entry.shortname,
                }
                for item_id, entry in sorted(self.entries.items())
            },
        }
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(
                self.cache_path.suffix + ".tmp"
            )
            temporary.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
                newline="\n",
            )
            temporary.replace(self.cache_path)
        except OSError as exc:
            self.last_error = f"Catalog loaded but cache write failed: {exc}"


def parse_item_catalog(payload: Any) -> dict[int, RustItemEntry]:
    entries: dict[int, RustItemEntry] = {}
    for record in _catalog_records(payload):
        item_id = _coerce_int(
            _field(record, "itemId", "itemid", "itemID", "ItemId", "id")
        )
        if item_id is None:
            continue

        name = _text_value(
            _field(
                record,
                "name",
                "displayName",
                "display_name",
                "localizedName",
                "label",
                "Name",
            )
        )
        shortname = _text_value(
            _field(
                record,
                "shortname",
                "shortName",
                "short_name",
                "Shortname",
            )
        )
        if not name:
            name = shortname
        if not name:
            continue

        entries[item_id] = RustItemEntry(
            item_id=item_id,
            name=name,
            shortname=shortname,
        )
    return entries


def _parse_cached_entries(
    payload: dict[str, Any],
) -> dict[int, RustItemEntry]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, dict):
        return {}
    entries: dict[int, RustItemEntry] = {}
    for raw_id, raw_entry in raw_items.items():
        item_id = _coerce_int(raw_id)
        if item_id is None or not isinstance(raw_entry, dict):
            continue
        name = str(raw_entry.get("name") or "").strip()
        shortname = str(raw_entry.get("shortname") or "").strip()
        if name:
            entries[item_id] = RustItemEntry(item_id, name, shortname)
    return entries


def _catalog_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("items", "Items", "data", "results"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        if isinstance(rows, dict):
            return [
                row
                for row in rows.values()
                if isinstance(row, dict)
            ]

    if _field(payload, "itemId", "itemid", "id") is not None:
        return [payload]

    return [
        row
        for row in payload.values()
        if isinstance(row, dict)
    ]


def _field(record: dict[str, Any], *aliases: str) -> Any:
    lowered = {str(key).casefold(): value for key, value in record.items()}
    for alias in aliases:
        if alias in record:
            return record[alias]
        candidate = lowered.get(alias.casefold())
        if candidate is not None:
            return candidate
    return None


def _text_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("english", "en", "value", "name", "displayName"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for candidate in value.values():
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _coerce_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _download_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "RustCompanionPlus/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Item catalog returned HTTP {exc.code}."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Item catalog could not be reached: {exc.reason}"
        ) from exc

    if not 200 <= status < 300:
        raise RuntimeError(f"Item catalog returned HTTP {status}.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Item catalog returned invalid JSON.") from exc
