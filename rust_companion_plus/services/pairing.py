from __future__ import annotations

import json
import queue
import re
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


_HOST_KEYS = {"ip", "host", "serverip", "server_ip", "address"}
_PORT_KEYS = {
    "port",
    "appport",
    "app_port",
    "app.port",
    "rustappport",
    "rust_app_port",
    "companionport",
    "companion_port",
}
_STEAM_KEYS = {"playerid", "player_id", "steamid", "steam_id"}
_TOKEN_KEYS = {"playertoken", "player_token", "token"}
_NAME_KEYS = {"name", "servername", "server_name"}


@dataclass(slots=True)
class PairingRecord:
    host: str = ""
    port: int = 0
    steam_id: int = 0
    player_token: int = 0
    server_name: str = ""
    source: str = ""
    raw: dict[str, Any] | None = None

    def is_complete(self) -> bool:
        return bool(
            self.host
            and 1 <= self.port <= 65535
            and self.steam_id > 0
            and self.player_token > 0
        )

    def matches_host(self, host: str) -> bool:
        return _normalize_host(self.host) == _normalize_host(host)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_pairing_payload(value: Any, *, source: str = "pairing_payload") -> PairingRecord | None:
    """Extract Rust+ pairing details from JSON, nested notification data, or a URL.

    Rust+ notifications commonly expose ``ip``, ``port``, ``playerId`` and
    ``playerToken``. This parser is intentionally tolerant because notification
    wrappers differ between libraries and versions.
    """
    if value is None:
        return None

    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8", errors="replace")

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        path = Path(text).expanduser()
        try:
            is_file = path.is_file()
        except OSError:
            is_file = False
        if is_file:
            try:
                return parse_pairing_payload(
                    json.loads(path.read_text(encoding="utf-8")),
                    source=f"pairing_file:{path}",
                )
            except (OSError, json.JSONDecodeError):
                return None
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = _payload_from_url(text)
            if decoded is None:
                return None
        return parse_pairing_payload(decoded, source=source)

    mappings = list(_walk_mappings(value))
    if not mappings:
        return None

    best: PairingRecord | None = None
    best_score = -1
    for mapping in mappings:
        normalized = {_normalize_key(key): child for key, child in mapping.items()}
        record = PairingRecord(
            host=_first_text(normalized, _HOST_KEYS),
            port=_first_int(normalized, _PORT_KEYS),
            steam_id=_first_int(normalized, _STEAM_KEYS),
            player_token=_first_int(normalized, _TOKEN_KEYS),
            server_name=_first_text(normalized, _NAME_KEYS),
            source=source,
            raw=dict(mapping),
        )
        score = sum(
            (
                4 if record.host else 0,
                4 if record.port else 0,
                3 if record.steam_id else 0,
                4 if record.player_token else 0,
                1 if record.server_name else 0,
            )
        )
        if score > best_score:
            best = record
            best_score = score

    if best is None or best_score <= 0:
        return None
    return best


def load_fcm_config(value: str | Path | dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value if isinstance(value.get("fcm_credentials"), dict) else None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and isinstance(payload.get("fcm_credentials"), dict) else None


class PairingNotificationInbox:
    """Queue Rust+ pairing notifications received by the rustplus FCM listener."""

    def __init__(self, fcm_config: dict[str, Any]) -> None:
        self.fcm_config = fcm_config
        self.records: queue.Queue[PairingRecord] = queue.Queue()
        self.errors: queue.Queue[Exception] = queue.Queue()
        self._started = False
        self._listener: Any = None

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        try:
            from rustplus import FCMListener
        except ImportError as exc:
            self.errors.put(exc)
            return

        inbox = self

        class Listener(FCMListener):
            def on_notification(self, obj, notification, data_message) -> None:  # type: ignore[override]
                for candidate in (data_message, notification, obj):
                    record = parse_pairing_payload(candidate, source="rustplus_fcm_notification")
                    if record is not None and record.port and record.player_token:
                        inbox.records.put(record)
                        return

        try:
            self._listener = Listener(self.fcm_config)
            self._listener.start(daemon=True)
        except Exception as exc:  # library/network failures are reported to the launcher
            self.errors.put(exc)

    def wait_for(
        self,
        host: str,
        *,
        timeout: float | None = None,
        process_alive: Callable[[], bool] | None = None,
    ) -> PairingRecord | None:
        self.start()
        deadline = None if timeout is None else __import__("time").monotonic() + timeout
        while True:
            if process_alive is not None and not process_alive():
                return None
            try:
                error = self.errors.get_nowait()
            except queue.Empty:
                pass
            else:
                raise RuntimeError(f"Rust+ notification listener failed: {error}") from error

            remaining = 1.0
            if deadline is not None:
                remaining = max(0.0, min(1.0, deadline - __import__("time").monotonic()))
                if remaining <= 0:
                    return None
            try:
                record = self.records.get(timeout=remaining)
            except queue.Empty:
                continue
            if not host or record.matches_host(host):
                return record


def save_fcm_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(config, indent=2), encoding="utf-8")
    temporary.replace(path)


def _walk_mappings(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mappings(child)
    elif hasattr(value, "__dict__"):
        try:
            yield from _walk_mappings(vars(value))
        except TypeError:
            return


def _payload_from_url(text: str) -> dict[str, Any] | None:
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if not parsed.scheme or not (parsed.query or parsed.fragment):
        return None
    values = parse_qs(parsed.query or parsed.fragment)
    return {key: rows[-1] for key, rows in values.items() if rows}


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_.]", "", str(value).casefold())


def _normalize_host(value: str) -> str:
    return value.strip().strip("[]").casefold()


def _first_text(mapping: dict[str, Any], keys: set[str]) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value).strip().strip("[]")
    return ""


def _first_int(mapping: dict[str, Any], keys: set[str]) -> int:
    for key in keys:
        value = mapping.get(key)
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 0
