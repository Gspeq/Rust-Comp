from __future__ import annotations

import socket
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable

from rust_companion_plus.services.http_client import request_json
from rust_companion_plus.services.server_detection import normalize_host


BATTLEMETRICS_API = "https://api.battlemetrics.com"


def _normal_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key), nested
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _detail(details: dict[str, Any], *names: str, default: Any = None) -> Any:
    wanted = {_normal_key(name) for name in names}
    for key, value in _walk(details):
        if _normal_key(key) in wanted and value not in (None, ""):
            return value
    return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class BattleMetricsServer:
    server_id: str
    name: str
    ip: str
    port: int
    query_port: int
    players: int
    max_players: int
    status: str
    rank: int = 0
    country: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    current_players: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_resource(cls, resource: dict[str, Any], included: list[dict[str, Any]] | None = None) -> "BattleMetricsServer":
        attributes = resource.get("attributes") or {}
        details = attributes.get("details") if isinstance(attributes.get("details"), dict) else {}
        current_players = [
            str(item.get("attributes", {}).get("name") or "")
            for item in (included or [])
            if item.get("type") == "player" and item.get("attributes", {}).get("name")
        ]
        return cls(
            server_id=str(resource.get("id") or ""),
            name=str(attributes.get("name") or "Unknown server"),
            ip=normalize_host(str(attributes.get("ip") or attributes.get("address") or "")),
            port=_as_int(attributes.get("port")),
            query_port=_as_int(
                attributes.get("portQuery")
                or attributes.get("queryPort")
                or _detail(details, "queryPort", "query_port", "rustQueryPort")
            ),
            players=_as_int(attributes.get("players")),
            max_players=_as_int(attributes.get("maxPlayers")),
            status=str(attributes.get("status") or "unknown"),
            rank=_as_int(attributes.get("rank")),
            country=str(attributes.get("country") or ""),
            details=details,
            created_at=str(attributes.get("createdAt") or ""),
            updated_at=str(attributes.get("updatedAt") or ""),
            current_players=current_players,
            raw=resource,
        )

    @property
    def seed(self) -> int:
        return _as_int(_detail(self.details, "rust_world_seed", "worldSeed", "seed"))

    @property
    def world_size(self) -> int:
        return _as_int(
            _detail(self.details, "rust_world_size", "rust_mapsize", "worldSize", "mapSize", "size")
        )

    @property
    def map_name(self) -> str:
        return str(_detail(self.details, "rust_map", "map", "mapName", default="Procedural Map"))

    @property
    def last_wipe(self) -> str:
        return str(_detail(self.details, "rust_last_wipe", "lastWipe", "wipe", default=""))

    @property
    def next_wipe(self) -> str:
        return str(_detail(self.details, "rust_next_wipe", "nextWipe", default=""))

    @property
    def queue(self) -> int:
        return _as_int(_detail(self.details, "rust_queued_players", "queuedPlayers", "queue"))

    @property
    def companion_port(self) -> int:
        return _as_int(
            _detail(self.details, "rust_app_port", "appPort", "companionPort", "rustPlusPort")
        )

    @property
    def description(self) -> str:
        return str(_detail(self.details, "rust_description", "description", default=""))

    @property
    def website(self) -> str:
        return str(_detail(self.details, "rust_url", "website", "url", default=""))

    def to_server_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.website,
            "map": self.map_name,
            "size": self.world_size,
            "map_size": self.world_size,
            "players": self.players,
            "max_players": self.max_players,
            "queued_players": self.queue,
            "seed": self.seed,
            "ip": self.ip,
            "port": self.port,
            "query_port": self.query_port,
            "battlemetrics_id": self.server_id,
            "rank": self.rank,
            "country": self.country,
            "status": self.status,
            "last_wipe": self.last_wipe,
            "next_wipe": self.next_wipe,
            "description": self.description,
        }


class BattleMetricsClient:
    def __init__(
        self,
        token: str = "",
        *,
        request: Callable[..., dict[str, Any]] = request_json,
        api_url: str = BATTLEMETRICS_API,
    ) -> None:
        self.token = token.strip()
        self.request = request
        self.api_url = api_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get_server(self, server_id: str, *, include_players: bool = False) -> BattleMetricsServer:
        query = {"include": "player"} if include_players else None
        payload = self.request(
            "GET",
            f"{self.api_url}/servers/{server_id}",
            query=query,
            headers=self._headers(),
        )
        return BattleMetricsServer.from_resource(payload.get("data") or {}, payload.get("included") or [])

    def search_servers(self, search: str, *, page_size: int = 20) -> list[BattleMetricsServer]:
        payload = self.request(
            "GET",
            f"{self.api_url}/servers",
            query={
                "filter[game]": "rust",
                "filter[search]": search,
                "filter[status]": "online",
                "page[size]": max(1, min(100, page_size)),
                "sort": "rank",
            },
            headers=self._headers(),
        )
        included = payload.get("included") or []
        return [BattleMetricsServer.from_resource(item, included) for item in payload.get("data") or []]

    def find_server(self, host: str, port: int = 0) -> BattleMetricsServer:
        normalized = normalize_host(host)
        searches = [f"{normalized}:{port}" if port else normalized]
        try:
            resolved = socket.gethostbyname(normalized)
        except OSError:
            resolved = ""
        if resolved and resolved != normalized:
            searches.append(f"{resolved}:{port}" if port else resolved)

        servers: list[BattleMetricsServer] = []
        seen: set[str] = set()
        for search in searches:
            for server in self.search_servers(search):
                if server.server_id not in seen:
                    servers.append(server)
                    seen.add(server.server_id)
            if servers:
                break
        if not servers:
            raise LookupError(f"BattleMetrics could not match a live Rust server for {host}:{port or '—'}.")

        def score(server: BattleMetricsServer) -> tuple[int, int]:
            points = 0
            server_host = normalize_host(server.ip)
            if server_host in {normalized, resolved}:
                points += 100
            if port and port in {server.port, server.query_port, server.companion_port}:
                points += 80
            if server.status.lower() == "online":
                points += 20
            return points, -server.rank if server.rank else -1_000_000

        return max(servers, key=score)
