from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any

from rust_companion_plus.config import STORE_PATH


DEFAULT_STORE: dict[str, Any] = {
    "credentials": {},
    "credential_profiles": {},
    "integration_settings": {},
    "electrical_setups": [],
    "threats": [],
    "resource_overlays": [],
    "notes": "",
    "loot_prices": {},
    "smart_devices": [],
    "heatmap_source_dir": "",
    "heatmap_world_size": 0,
    "heatmap_selected_resources": ["Stone", "Metal", "Sulfur"],
}


class JsonStore:
    """Tiny atomic JSON document store suitable for a single-user desktop app."""

    def __init__(self, path: Path = STORE_PATH) -> None:
        self.path = path
        self._lock = RLock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_STORE)
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            merged = dict(DEFAULT_STORE)
            merged.update(loaded)
            return merged
        except (OSError, json.JSONDecodeError):
            backup = self.path.with_suffix(".corrupt.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            return dict(DEFAULT_STORE)

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._flush()

    def append(self, key: str, value: Any) -> None:
        with self._lock:
            items = list(self._data.get(key, []))
            items.append(value)
            self._data[key] = items
            self._flush()

    def replace_all(self, data: dict[str, Any]) -> None:
        with self._lock:
            merged = dict(DEFAULT_STORE)
            merged.update(data)
            self._data = merged
            self._flush()
