from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from rust_companion_plus.config import APP_DATA_DIR
from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.battlemetrics_client import BattleMetricsClient, BattleMetricsServer
from rust_companion_plus.services.resource_heatmaps import (
    ResourceHeatmapBundle,
    find_map_parser,
    load_heatmap_bundle,
    parse_local_map,
)
from rust_companion_plus.services.rustmaps_client import RustMapMetadata, RustMapsClient
from rust_companion_plus.services import rustplus_client as rustplus_client_module
from rust_companion_plus.services.rustplus_client import RustPlusClient
from rust_companion_plus.services.server_detection import (
    ServerCandidate,
    ServerDetectionError,
    ServerDetector,
    hosts_equivalent,
    normalize_host,
)


@dataclass(slots=True)
class IntegrationSettings:
    auto_detect_server: bool = True
    auto_sync_enabled: bool = True
    sync_interval_seconds: int = 60
    battlemetrics_token: str = ""
    battlemetrics_include_players: bool = False
    rustmaps_api_key: str = ""
    rustmaps_auto_generate: bool = False
    rustmaps_download_map: bool = True
    auto_parse_map: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "IntegrationSettings":
        data = data or {}
        return cls(
            auto_detect_server=bool(data.get("auto_detect_server", True)),
            auto_sync_enabled=bool(data.get("auto_sync_enabled", True)),
            sync_interval_seconds=max(30, min(3600, int(data.get("sync_interval_seconds", 60) or 60))),
            battlemetrics_token=str(data.get("battlemetrics_token", "") or ""),
            battlemetrics_include_players=bool(data.get("battlemetrics_include_players", False)),
            rustmaps_api_key=str(data.get("rustmaps_api_key", "") or ""),
            rustmaps_auto_generate=bool(data.get("rustmaps_auto_generate", False)),
            rustmaps_download_map=bool(data.get("rustmaps_download_map", True)),
            auto_parse_map=bool(data.get("auto_parse_map", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LiveSyncResult:
    detected: ServerCandidate | None = None
    battlemetrics_server: BattleMetricsServer | None = None
    rustmaps_map: RustMapMetadata | None = None
    credentials: RustCredentials = field(default_factory=RustCredentials)
    snapshot: rustplus_client_module.ServerSnapshot | None = None
    rustplus_connected: bool = False
    map_image: Image.Image | None = None
    heatmap_bundle: ResourceHeatmapBundle | None = None
    map_cache_dir: Path | None = None
    warnings: list[str] = field(default_factory=list)
    synced_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def summary(self) -> str:
        server_name = "No server"
        if self.battlemetrics_server:
            server_name = self.battlemetrics_server.name
        elif self.snapshot:
            server_name = str(self.snapshot.server.get("name") or "Detected server")
        source = self.detected.source if self.detected else "manual profile"
        suffix = f" Â· {len(self.warnings)} warning(s)" if self.warnings else ""
        return f"Synced {server_name} via {source}{suffix}"


def _safe_cache_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_." else "_" for character in value)


def _profile_candidates(
    current: RustCredentials,
    profiles: dict[str, Any] | None,
    host: str,
    server_id: str = "",
) -> list[RustCredentials]:
    rows: list[RustCredentials] = [current]
    for key, raw in (profiles or {}).items():
        if not isinstance(raw, dict):
            continue
        credentials = RustCredentials.from_dict(raw)
        key_text = str(key)
        if server_id and key_text == server_id:
            rows.insert(0, credentials)
        elif credentials.host and hosts_equivalent(credentials.host, host):
            rows.insert(0, credentials)
        else:
            rows.append(credentials)
    return rows


def _select_credentials(
    current: RustCredentials,
    profiles: dict[str, Any] | None,
    host: str,
    server_id: str = "",
    companion_port: int = 0,
) -> RustCredentials:
    for candidate in _profile_candidates(current, profiles, host, server_id):
        if candidate.host and hosts_equivalent(candidate.host, host) and candidate.steam_id and candidate.player_token:
            return RustCredentials(
                host=host,
                port=companion_port or candidate.port,
                steam_id=candidate.steam_id,
                player_token=candidate.player_token,
            )
    return RustCredentials(
        host=host,
        port=companion_port or (current.port if current.host and hosts_equivalent(current.host, host) else 0),
        steam_id=current.steam_id if current.host and hosts_equivalent(current.host, host) else 0,
        player_token=current.player_token if current.host and hosts_equivalent(current.host, host) else 0,
    )


class LiveSyncService:
    def __init__(
        self,
        *,
        detector: ServerDetector | None = None,
        rustplus: RustPlusClient | None = None,
    ) -> None:
        self.detector = detector or ServerDetector()
        self.rustplus = rustplus or RustPlusClient()

    def _resolve_server(
        self,
        settings: IntegrationSettings,
        credentials: RustCredentials,
    ) -> tuple[ServerCandidate, BattleMetricsServer | None, list[str]]:
        warnings: list[str] = []
        if settings.auto_detect_server:
            candidates = self.detector.detect_all(credentials.host, credentials.port)
        elif credentials.host:
            candidates = [ServerCandidate(credentials.host, credentials.port, "Saved Rust+ profile", 20)]
        else:
            raise ServerDetectionError("Auto-detection is disabled and no saved server host is available.")
        if not candidates:
            raise ServerDetectionError("No active Rust server endpoint was detected.")

        bm = BattleMetricsClient(settings.battlemetrics_token)
        for candidate in candidates[:8]:
            try:
                server = bm.find_server(candidate.host, candidate.port)
                if settings.battlemetrics_include_players and settings.battlemetrics_token:
                    try:
                        server = bm.get_server(server.server_id, include_players=True)
                    except Exception as exc:
                        warnings.append(f"BattleMetrics player list was unavailable: {exc}")
                return candidate, server, warnings
            except Exception:
                continue
        warnings.append(
            "BattleMetrics could not verify the detected endpoint; using the strongest local detection candidate."
        )
        return candidates[0], None, warnings

    def refresh(
        self,
        credentials: RustCredentials,
        settings: IntegrationSettings,
        *,
        credential_profiles: dict[str, Any] | None = None,
    ) -> LiveSyncResult:
        detected, bm_server, warnings = self._resolve_server(settings, credentials)
        host = bm_server.ip if bm_server and bm_server.ip else normalize_host(detected.host)
        selected_credentials = _select_credentials(
            credentials,
            credential_profiles,
            host,
            bm_server.server_id if bm_server else "",
            bm_server.companion_port if bm_server else 0,
        )
        result = LiveSyncResult(
            detected=detected,
            battlemetrics_server=bm_server,
            credentials=selected_credentials,
            warnings=warnings,
        )

        rust_snapshot: rustplus_client_module.ServerSnapshot | None = None
        if selected_credentials.is_complete():
            try:
                rust_snapshot = self.rustplus.fetch_snapshot(selected_credentials)
                result.rustplus_connected = True
            except Exception as exc:
                result.warnings.append(f"Rust+ live data was unavailable for this server profile: {exc}")
        else:
            result.warnings.append(
                "No matching Rust+ token profile is saved for this server; BattleMetrics and RustMaps still update automatically."
            )

        if rust_snapshot is None and bm_server is not None:
            rust_snapshot = rustplus_client_module.ServerSnapshot(bm_server.to_server_dict(), [], [], "")
        elif rust_snapshot is not None and bm_server is not None:
            merged = bm_server.to_server_dict()
            merged.update({key: value for key, value in rust_snapshot.server.items() if value not in (None, "", 0)})
            # BattleMetrics is preferred for fields Rust+ normally does not expose.
            for key in (
                "battlemetrics_id",
                "rank",
                "country",
                "status",
                "last_wipe",
                "next_wipe",
                "description",
                "ip",
                "port",
                "query_port",
            ):
                merged[key] = bm_server.to_server_dict().get(key)
            rust_snapshot.server = merged
        result.snapshot = rust_snapshot

        size = 0
        seed = 0
        if rust_snapshot:
            size = int(rust_snapshot.server.get("size") or rust_snapshot.server.get("map_size") or 0)
            seed = int(rust_snapshot.server.get("seed") or 0)
        if bm_server:
            size = bm_server.world_size or size
            seed = bm_server.seed or seed

        if settings.rustmaps_api_key and size and seed:
            rustmaps = RustMapsClient(settings.rustmaps_api_key)
            try:
                metadata = rustmaps.ensure_map(size, seed, auto_generate=settings.rustmaps_auto_generate)
            except Exception as exc:
                result.warnings.append(f"RustMaps lookup failed: {exc}")
                metadata = None
            result.rustmaps_map = metadata
            if metadata is None:
                result.warnings.append("RustMaps is generating this map or has not finished indexing it yet.")
            else:
                cache_key = metadata.map_id or f"{metadata.size}_{metadata.seed}"
                cache_dir = APP_DATA_DIR / "live_maps" / _safe_cache_name(cache_key)
                cache_dir.mkdir(parents=True, exist_ok=True)
                result.map_cache_dir = cache_dir
                (cache_dir / "rustmaps_metadata.json").write_text(
                    json.dumps(metadata.raw, indent=2), encoding="utf-8"
                )
                map_image_path = cache_dir / "map_texture.png"
                map_path = cache_dir / f"{metadata.size}_{metadata.seed}.map"
                needs_map = (
                    settings.rustmaps_download_map
                    and settings.auto_parse_map
                    and metadata.can_download
                    and bool(metadata.download_url)
                    and not map_path.exists()
                )
                try:
                    if not map_image_path.exists() or needs_map:
                        assets = rustmaps.download_assets(
                            metadata,
                            cache_dir,
                            include_map_file=needs_map,
                        )
                        if assets.map_file:
                            map_path = assets.map_file
                    if map_image_path.exists():
                        result.map_image = rustmaps.open_image(map_image_path)
                except Exception as exc:
                    result.warnings.append(f"RustMaps asset download failed: {exc}")

                parsed_dir = cache_dir / "parsed"
                if settings.auto_parse_map and map_path.exists():
                    parser = find_map_parser()
                    if parser is None:
                        result.warnings.append(
                            "The map file is cached, but MapParser.exe was not found; exact resource layers cannot be rebuilt yet."
                        )
                    else:
                        try:
                            if not (parsed_dir / "map_resolved.json").exists():
                                parse_local_map(map_path, parsed_dir, parser)
                            result.heatmap_bundle = load_heatmap_bundle(parsed_dir, size)
                        except Exception as exc:
                            result.warnings.append(f"Automatic map parsing failed: {exc}")
                elif settings.auto_parse_map and not metadata.can_download:
                    result.warnings.append(
                        "RustMaps does not permit downloading this .map with the current subscription/map, so exact node parsing is unavailable."
                    )

        if result.map_image is None and selected_credentials.is_complete():
            try:
                result.map_image = self.rustplus.fetch_map(selected_credentials)
            except Exception as exc:
                result.warnings.append(f"Rust+ map rendering failed: {exc}")

        return result
