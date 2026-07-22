from __future__ import annotations

import asyncio
from typing import Any, Iterable

from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.rustplus_client import (
    RustPlusClient,
    RustPlusRequestError,
)


ENTITY_FIELDS = (
    "type",
    "value",
    "capacity",
    "has_protection",
    "protection_expiry",
)


def _public_entity_fields(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in ENTITY_FIELDS:
        field = getattr(value, name, None)
        if isinstance(field, (str, int, float, bool)) or field is None:
            result[name] = field
    return result


def _clean_ids(entity_ids: Iterable[int]) -> list[int]:
    values: list[int] = []
    seen: set[int] = set()
    for raw in entity_ids:
        try:
            entity_id = int(raw)
        except (TypeError, ValueError):
            continue
        if entity_id <= 0 or entity_id in seen:
            continue
        seen.add(entity_id)
        values.append(entity_id)
    return values


def fetch_entities(
    client: RustPlusClient,
    credentials: RustCredentials,
    entity_ids: Iterable[int],
) -> dict[int, dict[str, Any]]:
    if not credentials.is_complete():
        raise RustPlusRequestError("Complete the Rust+ profile first.")
    ids = _clean_ids(entity_ids)
    if not ids:
        return {}
    return asyncio.run(_fetch_entities(client, credentials, ids))


async def _fetch_entities(
    client: RustPlusClient,
    credentials: RustCredentials,
    entity_ids: list[int],
) -> dict[int, dict[str, Any]]:
    RustError, RustSocket, ServerDetails = client._imports()
    details = ServerDetails(
        credentials.host,
        credentials.port,
        credentials.steam_id,
        credentials.player_token,
    )
    socket = RustSocket(details)
    results: dict[int, dict[str, Any]] = {}
    try:
        await socket.connect()
        for entity_id in entity_ids:
            try:
                value = await socket.get_entity_info(entity_id)
            except Exception as exc:
                results[entity_id] = {"error": str(exc)}
                continue
            if isinstance(value, RustError):
                results[entity_id] = {
                    "error": str(getattr(value, "reason", "Entity request failed"))
                }
            else:
                results[entity_id] = _public_entity_fields(value)
        return results
    finally:
        try:
            await socket.disconnect()
        except Exception:
            pass


def set_entities_value(
    client: RustPlusClient,
    credentials: RustCredentials,
    entity_ids: Iterable[int],
    value: bool,
) -> dict[int, dict[str, Any]]:
    if not credentials.is_complete():
        raise RustPlusRequestError("Complete the Rust+ profile first.")
    ids = _clean_ids(entity_ids)
    if not ids:
        return {}
    return asyncio.run(
        _set_entities_value(client, credentials, ids, bool(value))
    )


async def _set_entities_value(
    client: RustPlusClient,
    credentials: RustCredentials,
    entity_ids: list[int],
    value: bool,
) -> dict[int, dict[str, Any]]:
    RustError, RustSocket, ServerDetails = client._imports()
    details = ServerDetails(
        credentials.host,
        credentials.port,
        credentials.steam_id,
        credentials.player_token,
    )
    socket = RustSocket(details)
    results: dict[int, dict[str, Any]] = {}
    try:
        await socket.connect()
        for entity_id in entity_ids:
            try:
                response = await socket.set_entity_value(entity_id, value)
            except Exception as exc:
                results[entity_id] = {"error": str(exc)}
                continue
            if isinstance(response, RustError):
                results[entity_id] = {
                    "error": str(getattr(response, "reason", "Entity update failed"))
                }
            else:
                results[entity_id] = {"value": value, "updated": True}
        return results
    finally:
        try:
            await socket.disconnect()
        except Exception:
            pass
