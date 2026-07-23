from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

from rust_companion_plus.models import RustCredentials


class RustPlusUnavailable(RuntimeError):
    pass


class RustPlusRequestError(RuntimeError):
    pass


@dataclass(slots=True)
class ServerSnapshot:
    server: dict[str, Any]
    team: list[dict[str, Any]]
    markers: list[dict[str, Any]]
    server_time: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _public_fields(obj: Any, names: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in names:
        value = getattr(obj, name, None)
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[name] = value
    return result


class RustPlusClient:
    """
    Short-lived Rust+ adapter.

    The GUI calls these synchronous methods from worker threads. A future version
    can replace this with a long-lived asyncio socket without changing tab code.
    """

    @staticmethod
    def available() -> bool:
        try:
            import rustplus  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _imports():
        try:
            from rustplus import RustError, RustSocket, ServerDetails
        except ImportError as exc:
            raise RustPlusUnavailable(
                "The optional 'rustplus' package is not installed. "
                "Install requirements.txt for live server features."
            ) from exc
        return RustError, RustSocket, ServerDetails

    def fetch_snapshot(self, credentials: RustCredentials) -> ServerSnapshot:
        if not credentials.is_complete():
            raise RustPlusRequestError("Complete the IP, port, Steam ID and player token first.")
        return asyncio.run(self._fetch_snapshot(credentials))

    async def _fetch_snapshot(self, credentials: RustCredentials) -> ServerSnapshot:
        RustError, RustSocket, ServerDetails = self._imports()
        details = ServerDetails(
            credentials.host,
            credentials.port,
            credentials.steam_id,
            credentials.player_token,
        )
        socket = RustSocket(details)
        try:
            await socket.connect()
            info = await socket.get_info()
            if isinstance(info, RustError):
                raise RustPlusRequestError(str(getattr(info, "reason", "Server info failed")))

            team_info = await socket.get_team_info()
            markers = await socket.get_markers()
            time_info = await socket.get_time()

            server = _public_fields(
                info,
                ["url", "name", "map", "size", "map_size", "players", "max_players", "queued_players", "seed"],
            )
            team_rows: list[dict[str, Any]] = []
            if not isinstance(team_info, RustError):
                for member in getattr(team_info, "members", []) or []:
                    team_rows.append(
                        _public_fields(
                            member,
                            [
                                "steam_id",
                                "name",
                                "x",
                                "y",
                                "is_online",
                                "spawn_time",
                                "is_alive",
                                "death_time",
                            ],
                        )
                    )

            marker_rows: list[dict[str, Any]] = []
            if not isinstance(markers, RustError):
                for marker in markers or []:
                    row = _public_fields(
                        marker,
                        ["id", "type", "x", "y", "steam_id", "rotation", "radius", "alpha", "name"],
                    )
                    orders = []
                    for order in getattr(marker, "sell_orders", []) or []:
                        orders.append(
                            _public_fields(
                                order,
                                [
                                    "item_id",
                                    "quantity",
                                    "currency_id",
                                    "cost_per_item",
                                    "item_is_blueprint",
                                    "currency_is_blueprint",
                                    "amount_in_stock",
                                ],
                            )
                        )
                    row["sell_orders"] = orders
                    marker_rows.append(row)

            server_time = ""
            if not isinstance(time_info, RustError):
                server_time = str(getattr(time_info, "time", ""))

            return ServerSnapshot(server, team_rows, marker_rows, server_time)
        finally:
            try:
                await socket.disconnect()
            except Exception:
                pass

    def fetch_team(
        self,
        credentials: RustCredentials,
    ) -> list[dict[str, Any]]:
        """Fetch only team state for accurate deaths without full marker scans."""
        if not credentials.is_complete():
            raise RustPlusRequestError(
                "Complete the IP, port, Steam ID and player token first."
            )
        return asyncio.run(self._fetch_team(credentials))

    async def _fetch_team(
        self,
        credentials: RustCredentials,
    ) -> list[dict[str, Any]]:
        RustError, RustSocket, ServerDetails = self._imports()
        details = ServerDetails(
            credentials.host,
            credentials.port,
            credentials.steam_id,
            credentials.player_token,
        )
        socket = RustSocket(details)
        try:
            await socket.connect()
            team_info = await socket.get_team_info()
            if isinstance(team_info, RustError):
                raise RustPlusRequestError(
                    str(getattr(team_info, "reason", "Team request failed"))
                )
            rows: list[dict[str, Any]] = []
            for member in getattr(team_info, "members", []) or []:
                rows.append(
                    _public_fields(
                        member,
                        [
                            "steam_id",
                            "name",
                            "x",
                            "y",
                            "is_online",
                            "spawn_time",
                            "is_alive",
                            "death_time",
                        ],
                    )
                )
            return rows
        finally:
            try:
                await socket.disconnect()
            except Exception:
                pass

    def fetch_map_variants(
        self,
        credentials: RustCredentials,
    ):
        """Fetch clean and icon-rendered maps through one Rust+ connection."""
        if not credentials.is_complete():
            raise RustPlusRequestError("Complete the Rust+ credentials first.")
        return asyncio.run(self._fetch_map_variants(credentials))

    async def _fetch_map_variants(
        self,
        credentials: RustCredentials,
    ):
        RustError, RustSocket, ServerDetails = self._imports()
        details = ServerDetails(
            credentials.host,
            credentials.port,
            credentials.steam_id,
            credentials.player_token,
        )
        socket = RustSocket(details)
        try:
            await socket.connect()
            clean_image = await socket.get_map(
                add_icons=False,
                add_events=False,
                add_vending_machines=False,
                add_team_positions=False,
                override_images={},
                add_grid=True,
            )
            if isinstance(clean_image, RustError):
                raise RustPlusRequestError(
                    str(getattr(clean_image, "reason", "Clean map request failed"))
                )
            icon_image = await socket.get_map(
                add_icons=True,
                add_events=True,
                add_vending_machines=True,
                add_team_positions=True,
                override_images={},
                add_grid=True,
            )
            if isinstance(icon_image, RustError):
                icon_image = clean_image.copy()
            return clean_image, icon_image
        finally:
            try:
                await socket.disconnect()
            except Exception:
                pass

    def fetch_map(self, credentials: RustCredentials):
        if not credentials.is_complete():
            raise RustPlusRequestError("Complete the Rust+ credentials first.")
        return asyncio.run(self._fetch_map(credentials))

    async def _fetch_map(self, credentials: RustCredentials):
        RustError, RustSocket, ServerDetails = self._imports()
        details = ServerDetails(
            credentials.host,
            credentials.port,
            credentials.steam_id,
            credentials.player_token,
        )
        socket = RustSocket(details)
        try:
            await socket.connect()
            image = await socket.get_map(
                add_icons=True,
                add_events=True,
                add_vending_machines=True,
                add_team_positions=True,
                override_images={},
                add_grid=True,
            )
            if isinstance(image, RustError):
                raise RustPlusRequestError(str(getattr(image, "reason", "Map request failed")))
            return image
        finally:
            try:
                await socket.disconnect()
            except Exception:
                pass

    def fetch_clean_map(self, credentials: RustCredentials):
        """Fetch a grid map without server, event, vending, or team icons."""
        if not credentials.is_complete():
            raise RustPlusRequestError("Complete the Rust+ credentials first.")
        return asyncio.run(self._fetch_clean_map(credentials))

    async def _fetch_clean_map(self, credentials: RustCredentials):
        RustError, RustSocket, ServerDetails = self._imports()
        details = ServerDetails(
            credentials.host,
            credentials.port,
            credentials.steam_id,
            credentials.player_token,
        )
        socket = RustSocket(details)
        try:
            await socket.connect()
            image = await socket.get_map(
                add_icons=False,
                add_events=False,
                add_vending_machines=False,
                add_team_positions=False,
                override_images={},
                add_grid=True,
            )
            if isinstance(image, RustError):
                raise RustPlusRequestError(
                    str(getattr(image, "reason", "Clean map request failed"))
                )
            return image
        finally:
            try:
                await socket.disconnect()
            except Exception:
                pass

    def get_entity(self, credentials: RustCredentials, entity_id: int) -> dict[str, Any]:
        return asyncio.run(self._get_entity(credentials, entity_id))

    async def _get_entity(self, credentials: RustCredentials, entity_id: int) -> dict[str, Any]:
        RustError, RustSocket, ServerDetails = self._imports()
        details = ServerDetails(credentials.host, credentials.port, credentials.steam_id, credentials.player_token)
        socket = RustSocket(details)
        try:
            await socket.connect()
            info = await socket.get_entity_info(entity_id)
            if isinstance(info, RustError):
                raise RustPlusRequestError(str(getattr(info, "reason", "Entity request failed")))
            return _public_fields(
                info,
                ["type", "value", "capacity", "has_protection", "protection_expiry"],
            )
        finally:
            try:
                await socket.disconnect()
            except Exception:
                pass

    def set_entity_value(
        self, credentials: RustCredentials, entity_id: int, value: bool
    ) -> None:
        asyncio.run(self._set_entity_value(credentials, entity_id, value))

    async def _set_entity_value(
        self, credentials: RustCredentials, entity_id: int, value: bool
    ) -> None:
        RustError, RustSocket, ServerDetails = self._imports()
        details = ServerDetails(credentials.host, credentials.port, credentials.steam_id, credentials.player_token)
        socket = RustSocket(details)
        try:
            await socket.connect()
            result = await socket.set_entity_value(entity_id, value)
            if isinstance(result, RustError):
                raise RustPlusRequestError(str(getattr(result, "reason", "Entity update failed")))
        finally:
            try:
                await socket.disconnect()
            except Exception:
                pass
