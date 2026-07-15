
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from rust_companion_plus.config import APP_DATA_DIR
from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.builtin_map_analyzer import (
    analyze_map_image,
)


PROFILE_STORE_KEY = "saved_server_profiles"
PROFILE_ROOT = APP_DATA_DIR / "server_profiles"
MAP_URL_RE = re.compile(
    r"https://maps\.rustmaps\.com/[^\s\"']+\.map",
    re.IGNORECASE,
)
PARSED_MARKERS = (
    "map_resolved.json",
    "map_data.json",
    "map_raw.json",
)

WORKSPACE_KEYS = (
    "notes",
    "threats",
    "electrical_setups",
    "smart_devices",
    "resource_overlays",
    "loot_prices",
    "heatmap_selected_resources",
    "threat_event_ids",
    "death_history",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_profile_folder_name(key: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(key)).strip("._")
    label = label[:60] or "server"
    digest = hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:10]
    return f"{label}-{digest}"


def profile_asset_dir(
    key: str,
    *,
    root: Path = PROFILE_ROOT,
) -> Path:
    path = Path(root) / _safe_profile_folder_name(key)
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_parsed_map_dir(
    key: str,
    *,
    root: Path = PROFILE_ROOT,
) -> Path:
    return profile_asset_dir(key, root=root) / "parsed_map"


def is_parsed_map_directory(path: str | Path) -> bool:
    candidate = Path(path)
    return candidate.is_dir() and any(
        (candidate / marker).is_file()
        for marker in PARSED_MARKERS
    )


def _snapshot_server(snapshot: dict[str, Any]) -> dict[str, Any]:
    server = snapshot.get("server") if isinstance(snapshot, dict) else {}
    return dict(server) if isinstance(server, dict) else {}


def _display_name(
    key: str,
    snapshot: dict[str, Any],
    detection: dict[str, Any],
) -> str:
    server = _snapshot_server(snapshot)
    for value in (
        server.get("name"),
        (detection.get("battlemetrics") or {}).get("name")
        if isinstance(detection.get("battlemetrics"), dict)
        else "",
        key,
    ):
        text = str(value or "").strip()
        if text:
            return text
    return key


def _selected_endpoint(detection: dict[str, Any]) -> str:
    selected = detection.get("selected") if isinstance(detection, dict) else {}
    if not isinstance(selected, dict):
        return ""
    return str(selected.get("endpoint") or "").strip()


def discover_current_map_url(
    detection: dict[str, Any] | None,
    profile_record: dict[str, Any] | None = None,
) -> str:
    record = profile_record if isinstance(profile_record, dict) else {}
    assets = record.get("assets") if isinstance(record.get("assets"), dict) else {}
    saved = str(assets.get("map_url") or "").strip()
    if saved:
        return saved

    report = detection if isinstance(detection, dict) else {}
    selected = report.get("selected")
    if isinstance(selected, dict):
        metadata = selected.get("metadata")
        if isinstance(metadata, dict):
            value = str(metadata.get("map_url") or "").strip()
            if value:
                return value

    candidates = report.get("candidates")
    if isinstance(candidates, list):
        for candidate in reversed(candidates):
            if not isinstance(candidate, dict):
                continue
            metadata = candidate.get("metadata")
            if not isinstance(metadata, dict):
                continue
            value = str(metadata.get("map_url") or "").strip()
            if value:
                return value

    log_path = str(report.get("log_path") or "").strip()
    if not log_path:
        return ""
    path = Path(log_path)
    if not path.is_file():
        return ""

    try:
        with path.open("rb") as handle:
            size = path.stat().st_size
            handle.seek(max(0, size - 8 * 1024 * 1024))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""

    matches = MAP_URL_RE.findall(text)
    return matches[-1] if matches else ""


def _map_filename_from_url(url: str) -> str:
    if not url:
        return "current_server.map"
    parsed = urllib.parse.urlparse(url)
    name = urllib.parse.unquote(Path(parsed.path).name)
    if name.casefold().endswith(".map"):
        return name
    return "current_server.map"


def _known_map_roots(
    detection: dict[str, Any],
    profile_dir: Path,
) -> list[Path]:
    roots = [profile_dir]
    log_path = str(detection.get("log_path") or "").strip()
    if log_path:
        log_parent = Path(log_path).expanduser().resolve(strict=False).parent
        roots.extend((log_parent, log_parent / "maps"))

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(
            Path(local_app_data)
            / ".."
            / "LocalLow"
            / "Facepunch Studios LTD"
            / "Rust"
        )

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        normalized = str(root.resolve(strict=False)).casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(root)
    return unique


def _iter_map_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    candidates: list[Path] = []
    try:
        candidates.extend(path for path in root.glob("*.map") if path.is_file())
        maps_dir = root / "maps"
        if maps_dir.is_dir():
            candidates.extend(
                path for path in maps_dir.rglob("*.map") if path.is_file()
            )
        if "facepunch studios ltd" in str(root).casefold():
            candidates.extend(
                path for path in root.rglob("*.map") if path.is_file()
            )
    except OSError:
        pass
    return candidates[:600]


def _find_existing_map_file(
    *,
    map_url: str,
    detection: dict[str, Any],
    profile_record: dict[str, Any],
    profile_dir: Path,
    world_size: int,
) -> Path | None:
    assets = (
        profile_record.get("assets")
        if isinstance(profile_record.get("assets"), dict)
        else {}
    )
    saved = str(assets.get("raw_map_path") or "").strip()
    if saved and Path(saved).is_file():
        return Path(saved)

    expected_name = _map_filename_from_url(map_url).casefold()
    candidates: list[tuple[int, float, Path]] = []

    for root in _known_map_roots(detection, profile_dir):
        for path in _iter_map_files(root):
            score = 0
            if path.name.casefold() == expected_name:
                score += 100
            if world_size and str(world_size) in path.name:
                score += 15
            if path.parent == profile_dir:
                score += 25
            try:
                modified = path.stat().st_mtime
            except OSError:
                modified = 0.0
            candidates.append((score, modified, path))

    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (row[0], row[1]),
        reverse=True,
    )
    return candidates[0][2]


def download_current_map(
    url: str,
    destination: str | Path,
) -> Path:
    parsed = urllib.parse.urlparse(url)
    host = str(parsed.hostname or "").casefold()
    if parsed.scheme.casefold() != "https":
        raise ValueError("The current map URL is not HTTPS.")
    if host != "maps.rustmaps.com":
        raise ValueError(
            "The current map URL is not hosted by maps.rustmaps.com."
        )
    if not parsed.path.casefold().endswith(".map"):
        raise ValueError("The current map URL does not point to a .map file.")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "RustCompanionPlus/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(getattr(response, "status", 200))
            if not 200 <= status < 300:
                raise RuntimeError(
                    f"RustMaps returned HTTP {status}."
                )
            total = 0
            with temporary.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > 750 * 1024 * 1024:
                        raise RuntimeError(
                            "The map download exceeded the 750 MB safety limit."
                        )
                    handle.write(chunk)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"RustMaps returned HTTP {exc.code}."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"The current map could not be downloaded: {exc.reason}"
        ) from exc
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    if not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("The current map download was empty.")
    temporary.replace(destination)
    return destination


@dataclass(frozen=True, slots=True)
class ParsedMapResult:
    source_dir: Path
    raw_map_path: Path | None
    map_url: str
    created: bool


def discover_saved_parsed_map(
    key: str,
    profile_record: dict[str, Any] | None,
    world_size: int,
    *,
    root: Path = PROFILE_ROOT,
) -> Path | None:
    record = profile_record if isinstance(profile_record, dict) else {}
    assets = record.get("assets") if isinstance(record.get("assets"), dict) else {}
    candidates: list[Path] = []
    saved_source = str(
        assets.get("parsed_map_dir") or ""
    ).strip()
    if saved_source:
        candidates.append(Path(saved_source))
    candidates.append(default_parsed_map_dir(key, root=root))
    for candidate in candidates:
        if is_parsed_map_directory(candidate):
            return candidate

    return None


def parse_current_server_map(
    *,
    key: str,
    detection: dict[str, Any],
    profile_record: dict[str, Any] | None,
    world_size: int,
    map_image: Image.Image | None = None,
    markers: Iterable[dict[str, Any]] | None = None,
    root: Path = PROFILE_ROOT,
) -> ParsedMapResult:
    """Analyze the current Rust+ map without an external executable."""
    record = profile_record if isinstance(
        profile_record,
        dict,
    ) else {}
    existing = discover_saved_parsed_map(
        key,
        record,
        world_size,
        root=root,
    )
    assets = (
        record.get("assets")
        if isinstance(record.get("assets"), dict)
        else {}
    )
    saved_raw = str(
        assets.get("raw_map_path") or ""
    ).strip()
    map_url = discover_current_map_url(
        detection,
        record,
    )
    if existing is not None:
        return ParsedMapResult(
            source_dir=existing,
            raw_map_path=(
                Path(saved_raw)
                if saved_raw
                else None
            ),
            map_url=map_url,
            created=False,
        )

    if map_image is None:
        raise ValueError(
            "The current Rust+ map image is not loaded. "
            "Use Load current map, then run Analyze current map."
        )

    output = default_parsed_map_dir(
        key,
        root=root,
    )
    if output.exists() and not is_parsed_map_directory(
        output
    ):
        shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True, exist_ok=True)

    analysis = analyze_map_image(
        map_image,
        output,
        world_size=world_size,
        markers=markers,
    )
    if not analysis.manifest_path.is_file():
        raise RuntimeError(
            "The built-in map analyzer did not produce its manifest."
        )

    return ParsedMapResult(
        source_dir=analysis.output_dir,
        raw_map_path=(
            Path(saved_raw)
            if saved_raw
            else None
        ),
        map_url=map_url,
        created=True,
    )



class ServerProfileVault:
    def __init__(
        self,
        store: Any,
        *,
        asset_root: Path = PROFILE_ROOT,
    ) -> None:
        self.store = store
        self.asset_root = Path(asset_root)

    def _profiles(self) -> dict[str, dict[str, Any]]:
        raw = self.store.get(PROFILE_STORE_KEY, {}) or {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): copy.deepcopy(value)
            for key, value in raw.items()
            if isinstance(value, dict)
        }

    def get(self, key: str) -> dict[str, Any] | None:
        value = self._profiles().get(str(key))
        return copy.deepcopy(value) if value is not None else None

    def list_profiles(self) -> list[dict[str, Any]]:
        rows = list(self._profiles().values())
        rows.sort(
            key=lambda row: str(
                row.get("live_updated_at")
                or row.get("saved_at")
                or ""
            ),
            reverse=True,
        )
        return rows

    def credentials_for(self, key: str) -> RustCredentials:
        profiles = self.store.get("credential_profiles", {}) or {}
        if isinstance(profiles, dict):
            value = profiles.get(key)
            if isinstance(value, dict):
                return RustCredentials.from_dict(value)
        return RustCredentials.from_dict(
            self.store.get("credentials", {}) or {}
        )

    def runtime_key(
        self,
        credentials: RustCredentials,
        detection: dict[str, Any],
    ) -> str:
        selected = _selected_endpoint(detection)
        if selected:
            return selected

        active = str(
            self.store.get("active_server_profile_key", "") or ""
        ).strip()
        if active:
            return active

        profiles = self.store.get("credential_profiles", {}) or {}
        if isinstance(profiles, dict):
            for key, raw in profiles.items():
                if not isinstance(raw, dict):
                    continue
                candidate = RustCredentials.from_dict(raw)
                if (
                    candidate.host.casefold()
                    == credentials.host.casefold()
                    and candidate.port == credentials.port
                    and candidate.steam_id == credentials.steam_id
                    and candidate.player_token == credentials.player_token
                ):
                    return str(key)
        return ""

    def workspace_snapshot(self) -> dict[str, Any]:
        return {
            key: copy.deepcopy(self.store.get(key))
            for key in WORKSPACE_KEYS
        }

    def apply_workspace(
        self,
        profile_record: dict[str, Any] | None,
    ) -> None:
        record = (
            profile_record
            if isinstance(profile_record, dict)
            else {}
        )
        workspace = record.get("workspace")
        if not isinstance(workspace, dict):
            return
        for key in WORKSPACE_KEYS:
            if key in workspace:
                self.store.set(
                    key,
                    copy.deepcopy(workspace[key]),
                )

    def save_map_image(
        self,
        key: str,
        image: Any,
    ) -> str:
        if image is None or not hasattr(image, "save"):
            return ""
        destination = (
            profile_asset_dir(key, root=self.asset_root)
            / "live_map.png"
        )
        temporary = destination.with_suffix(".tmp.png")
        image.save(temporary, format="PNG")
        temporary.replace(destination)
        return str(destination)

    def load_map_image(
        self,
        profile_record: dict[str, Any] | None,
    ) -> Image.Image | None:
        record = profile_record if isinstance(profile_record, dict) else {}
        assets = record.get("assets") if isinstance(record.get("assets"), dict) else {}
        raw_path = str(assets.get("map_image_path") or "").strip()
        if not raw_path:
            return None
        path = Path(raw_path)
        if not path.is_file():
            return None
        try:
            with Image.open(path) as image:
                return image.convert("RGBA").copy()
        except OSError:
            return None

    def save_runtime_profile(
        self,
        *,
        key: str,
        credentials: RustCredentials,
        snapshot: dict[str, Any] | None,
        detection: dict[str, Any] | None,
        timeline: list[dict[str, Any]] | None,
        map_image: Any = None,
        pending_assets: dict[str, Any] | None = None,
        parsed_map_dir: str = "",
        heatmap_world_size: int = 0,
        heatmap_selected_resources: list[str] | None = None,
        live_updated_at: str = "",
    ) -> dict[str, Any]:
        key = str(key).strip()
        if not key:
            raise ValueError("A game-server profile key is required.")

        profiles = self._profiles()
        existing = profiles.get(key, {})
        existing_snapshot = (
            existing.get("snapshot")
            if isinstance(existing.get("snapshot"), dict)
            else {}
        )
        current_snapshot = (
            copy.deepcopy(snapshot)
            if isinstance(snapshot, dict) and snapshot
            else copy.deepcopy(existing_snapshot)
        )
        current_detection = (
            copy.deepcopy(detection)
            if isinstance(detection, dict) and detection
            else copy.deepcopy(existing.get("detection") or {})
        )
        current_timeline = (
            copy.deepcopy(timeline[-250:])
            if isinstance(timeline, list) and timeline
            else copy.deepcopy(existing.get("timeline") or [])
        )

        assets = dict(
            existing.get("assets")
            if isinstance(existing.get("assets"), dict)
            else {}
        )
        if isinstance(pending_assets, dict):
            assets.update(
                {
                    str(name): value
                    for name, value in pending_assets.items()
                    if value not in (None, "")
                }
            )

        map_path = self.save_map_image(key, map_image)
        if map_path:
            assets["map_image_path"] = map_path
        if parsed_map_dir:
            assets["parsed_map_dir"] = str(parsed_map_dir)
        if heatmap_world_size:
            assets["world_size"] = int(heatmap_world_size)
        if heatmap_selected_resources is not None:
            assets["selected_resources"] = list(
                heatmap_selected_resources
            )

        map_url = discover_current_map_url(
            current_detection,
            {"assets": assets},
        )
        if map_url:
            assets["map_url"] = map_url

        server = _snapshot_server(current_snapshot)
        now = _now_iso()
        record = {
            "version": 1,
            "key": key,
            "name": _display_name(
                key,
                current_snapshot,
                current_detection,
            ),
            "game_endpoint": (
                _selected_endpoint(current_detection) or key
            ),
            "rustplus_endpoint": (
                f"{credentials.host}:{credentials.port}"
                if credentials.host and credentials.port
                else ""
            ),
            "credential_profile_key": key,
            "saved_at": now,
            "live_updated_at": (
                live_updated_at
                or str(existing.get("live_updated_at") or "")
                or now
            ),
            "snapshot": current_snapshot,
            "detection": current_detection,
            "timeline": current_timeline,
            "assets": assets,
            "workspace": self.workspace_snapshot(),
            "summary": {
                "map": str(
                    server.get("map")
                    or server.get("map_name")
                    or ""
                ),
                "world_size": int(
                    server.get("size")
                    or server.get("map_size")
                    or assets.get("world_size")
                    or 0
                ),
                "players": int(server.get("players") or 0),
                "max_players": int(
                    server.get("max_players") or 0
                ),
                "team_members": len(
                    current_snapshot.get("team") or []
                ),
                "markers": len(
                    current_snapshot.get("markers") or []
                ),
            },
            "capabilities": [
                "cached_server_info",
                "cached_team",
                "cached_shops_and_markers",
                "cached_timeline",
                "saved_map_assets",
                "live_rustplus_without_rust_process",
            ],
        }

        profiles[key] = record
        self.store.set(PROFILE_STORE_KEY, profiles)
        self.store.set("active_server_profile_key", key)
        return copy.deepcopy(record)
