from __future__ import annotations
from rust_companion_plus.models import normalize_player_token
import os
from rust_companion_plus.config import APP_DATA_DIR

import json
import queue
import re
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


_HOST_KEYS = (
    "serverip",
    "server_ip",
    "host",
    "ip",
    "address",
)
_PORT_KEYS = (
    "rust_app_port",
    "rustappport",
    "app_port",
    "app.port",
    "companion_port",
    "companionport",
    "appport",
    "port",
)
_STEAM_KEYS = (
    "playerid",
    "player_id",
    "steamid",
    "steam_id",
)
_TOKEN_KEYS = (
    "playertoken",
    "player_token",
)
_NAME_KEYS = (
    "servername",
    "server_name",
    "name",
)


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
            and 1 <= int(self.port) <= 65535
            and int(self.steam_id) > 0
            and int(self.player_token) != 0
        )

    def matches_host(self, host: str) -> bool:
        return _normalize_host(self.host) == _normalize_host(host)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)



def parse_pairing_payload(
    value: Any,
    *,
    source: str = "pairing_payload",
) -> PairingRecord | None:
    if value is None:
        return None

    if isinstance(value, (bytes, bytearray, memoryview)):
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

    candidates: list[tuple[int, PairingRecord]] = []
    for mapping in mappings:
        normalized = {
            _normalize_key(key): child
            for key, child in mapping.items()
        }
        record = PairingRecord(
            host=_first_text(normalized, _HOST_KEYS),
            port=_first_int(normalized, _PORT_KEYS),
            steam_id=_first_int(normalized, _STEAM_KEYS),
            player_token=_first_player_token(normalized, _TOKEN_KEYS),
            server_name=_first_text(normalized, _NAME_KEYS),
            source=source,
            raw=dict(mapping),
        )
        score = sum(
            (
                4 if record.host else 0,
                4 if record.port else 0,
                3 if record.steam_id else 0,
                6 if record.player_token else 0,
                1 if record.server_name else 0,
            )
        )
        if score > 0:
            candidates.append((score, record))

    if not candidates:
        return None

    candidates.sort(key=lambda row: row[0], reverse=True)
    merged = candidates[0][1]
    for _score, candidate in candidates[1:]:
        merged = _merge_pairing_records(merged, candidate)
    return merged




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


def _merge_pairing_records(
    current: PairingRecord | None,
    incoming: PairingRecord | None,
) -> PairingRecord:
    if current is None and incoming is None:
        return PairingRecord()
    if current is None:
        assert incoming is not None
        return PairingRecord(
            host=incoming.host,
            port=incoming.port,
            steam_id=incoming.steam_id,
            player_token=incoming.player_token,
            server_name=incoming.server_name,
            source=incoming.source,
            raw=incoming.raw,
        )
    if incoming is None:
        return current

    # A later record carrying the final token owns the Rust+ endpoint.
    prefer_incoming_endpoint = bool(incoming.player_token)
    host = (
        incoming.host
        if prefer_incoming_endpoint and incoming.host
        else current.host or incoming.host
    )
    port = (
        incoming.port
        if prefer_incoming_endpoint and incoming.port
        else current.port or incoming.port
    )
    return PairingRecord(
        host=host,
        port=port,
        steam_id=incoming.steam_id or current.steam_id,
        player_token=incoming.player_token or current.player_token,
        server_name=incoming.server_name or current.server_name,
        source=incoming.source or current.source,
        raw=incoming.raw or current.raw,
    )


def _pairing_record_has_signal(record: PairingRecord | None) -> bool:
    if record is None:
        return False
    return bool(
        record.host
        or record.port
        or record.steam_id
        or record.player_token
        or record.server_name
    )


def _pairing_missing_fields(record: PairingRecord) -> list[str]:
    missing: list[str] = []
    if not record.host:
        missing.append("Rust+ host")
    if not record.port:
        missing.append("Rust+ port")
    if not record.steam_id:
        missing.append("Steam ID")
    if not record.player_token:
        missing.append("player token")
    return missing

def _first_player_token(
    mapping: dict[str, Any],
    keys: Any,
) -> int:
    for key in keys:
        value = mapping.get(key)
        try:
            parsed = normalize_player_token(value)
        except (TypeError, ValueError):
            continue
        if parsed != 0:
            return parsed

    has_pairing_context = bool(
        _first_text(mapping, _HOST_KEYS)
        and _first_int(mapping, _PORT_KEYS)
        and _first_int(mapping, _STEAM_KEYS)
    )
    if has_pairing_context and "token" in mapping:
        try:
            parsed = normalize_player_token(mapping.get("token"))
        except (TypeError, ValueError):
            return 0
        return parsed if parsed != 0 else 0
    return 0



def _decode_push_value(value: Any) -> Any:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    return value


def _iter_app_data_entries(
    app_data: Any,
) -> list[tuple[str, Any]]:
    if app_data is None:
        return []
    if isinstance(app_data, dict):
        return [
            (str(key), _decode_push_value(value))
            for key, value in app_data.items()
            if str(key).strip()
        ]
    try:
        raw_entries = list(app_data)
    except TypeError:
        return []

    rows: list[tuple[str, Any]] = []
    for item in raw_entries:
        if isinstance(item, dict):
            key = item.get("key")
            child = item.get("value")
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            key, child = item[0], item[1]
        else:
            key = getattr(item, "key", "")
            child = getattr(item, "value", None)
        if key is None or not str(key).strip():
            continue
        rows.append((str(key), _decode_push_value(child)))
    return rows


def _app_data_entry_count(value: Any) -> int:
    return len(
        _iter_app_data_entries(
            getattr(value, "app_data", None)
        )
    )


def _normalized_server_label(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "",
        str(value or "").casefold(),
    )


def _is_conflicting_delayed_authorization(
    current: PairingRecord | None,
    incoming: PairingRecord,
) -> bool:
    if current is None or current.is_complete():
        return False
    if not incoming.player_token:
        return False
    if not current.host or not incoming.host:
        return False
    if current.matches_host(incoming.host):
        return False
    current_name = _normalized_server_label(current.server_name)
    incoming_name = _normalized_server_label(incoming.server_name)
    return bool(
        current_name
        and incoming_name
        and current_name != incoming_name
    )

def _coerce_data_message_mapping(
    value: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(value, dict):
        result.update(value)

    for key, child in _iter_app_data_entries(
        getattr(value, "app_data", None)
    ):
        result[key] = child

    if not isinstance(value, dict) and hasattr(value, "__dict__"):
        try:
            attributes = vars(value)
        except TypeError:
            attributes = {}
        for key, child in attributes.items():
            if str(key).startswith("_") or key == "app_data":
                continue
            child = _decode_push_value(child)
            if isinstance(
                child,
                (
                    str,
                    int,
                    float,
                    bool,
                    bytes,
                    bytearray,
                    memoryview,
                    dict,
                    list,
                    tuple,
                ),
            ) or child is None:
                result.setdefault(str(key), child)

    return result



def _debug_event(
    name: str,
    **fields: Any,
) -> None:
    # Low-level events now use the ordinary production logger.
    # No debug runtime, bundle collector, or bootloader hook is needed.
    try:
        import logging

        logging.getLogger(
            "rust_companion_plus.pairing"
        ).debug("%s %s", name, fields)
    except Exception:
        return


class PairingNotificationInbox:
    # Supervise and correlate multi-stage Rust+ pairing notifications.

    def __init__(self, fcm_config: dict[str, Any]) -> None:
        self.fcm_config = fcm_config
        self.records: queue.Queue[PairingRecord] = queue.Queue()
        self.errors: queue.Queue[Exception] = queue.Queue()
        self._started = False
        self._listener: Any = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._fatal_error: Exception | None = None

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        try:
            import logging
            from push_receiver import PushReceiver
        except ImportError as exc:
            self._fatal_error = exc
            self.errors.put(exc)
            return

        inbox = self

        def on_notification(
            obj: Any,
            notification: Any,
            data_message: Any,
        ) -> None:
            inbox._ready.set()
            normalized_data = _coerce_data_message_mapping(
                data_message
            )
            _debug_event(
                "pairing_data_message_normalized",
                keys=sorted(normalized_data.keys()),
                app_data_count=_app_data_entry_count(data_message),
                body_present=bool(normalized_data.get("body")),
                channel_id=str(normalized_data.get("channelId") or ""),
            )
            print(
                "[RUST+ PUSH] Notification received; "
                "decoding and correlating pairing data..."
            )
            try:
                _append_payload_diagnostic(
                    notification,
                    normalized_data,
                    obj,
                )
            except Exception as diagnostic_error:
                print(
                    "[RUST+ DEBUG] Safe payload-structure capture failed: "
                    f"{type(diagnostic_error).__name__}: "
                    f"{diagnostic_error}"
                )

            combined: PairingRecord | None = None
            for candidate_name, candidate in (
                ("normalized_app_data", normalized_data),
                ("notification", notification),
                ("data_message", data_message),
                ("callback_object", obj),
            ):
                try:
                    record = parse_pairing_payload(
                        candidate,
                        source="rustplus_fcm_notification",
                    )
                except Exception as parse_error:
                    _debug_event(
                        "pairing_candidate_parse_failed",
                        candidate=candidate_name,
                        exception_type=type(parse_error).__name__,
                        message=str(parse_error),
                    )
                    continue
                combined = _merge_pairing_records(combined, record)

            if not _pairing_record_has_signal(combined):
                print(
                    "[RUST+ PUSH] Notification contained no usable "
                    "Rust+ pairing fields."
                )
                return

            assert combined is not None
            inbox.records.put(combined)
            summary = {
                "host": combined.host,
                "port": combined.port,
                "steam_present": bool(combined.steam_id),
                "player_token_present": combined.player_token != 0,
                "player_token_sign": (
                    "negative"
                    if combined.player_token < 0
                    else "positive"
                    if combined.player_token > 0
                    else "missing"
                ),
                "server_name": combined.server_name,
                "complete": combined.is_complete(),
            }
            _debug_event("pairing_notification_correlated", record=summary)

            server = combined.server_name or combined.host or "unknown server"
            if combined.is_complete():
                print(
                    "[RUST+ PUSH] Complete pairing authorization "
                    f"decoded for {server}."
                )
            else:
                missing = ", ".join(_pairing_missing_fields(combined))
                endpoint = f"{combined.host or '?'}:{combined.port or '?'}"
                print(
                    "[RUST+ PUSH] Fresh pairing request observed for "
                    f"{server} at {endpoint}; waiting for {missing}."
                )

        class ReadyHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                if "Received login response" in record.getMessage():
                    inbox._ready.set()

        def worker() -> None:
            logger = logging.getLogger("push_receiver")
            old_level = logger.level
            old_propagate = logger.propagate
            handler = ReadyHandler()
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
            try:
                credentials = self.fcm_config.get("fcm_credentials")
                if not isinstance(credentials, dict):
                    raise RuntimeError("Saved FCM credentials are missing.")
                self._listener = PushReceiver(credentials=credentials)
                self._listener.listen(callback=on_notification)
            except Exception as exc:
                self._fatal_error = exc
                self.errors.put(exc)
            finally:
                logger.removeHandler(handler)
                logger.setLevel(old_level)
                logger.propagate = old_propagate

        self._thread = threading.Thread(
            target=worker,
            name="rustplus-supervised-push-receiver",
            daemon=True,
        )
        self._thread.start()


    def wait_until_ready(self, timeout: float = 12.0) -> bool:
        self.start()
        clock = __import__("time")
        deadline = clock.monotonic() + timeout
        while not self._ready.wait(0.20):
            if self._fatal_error is not None:
                raise RuntimeError(
                    f"Rust+ notification listener failed: "
                    f"{self._fatal_error}"
                ) from self._fatal_error
            if self._thread is not None and not self._thread.is_alive():
                raise RuntimeError(
                    "Rust+ notification listener stopped before connecting."
                )
            if clock.monotonic() >= deadline:
                _debug_event(
                    "pairing_receiver_ready_timeout",
                    timeout=timeout,
                    thread_alive=bool(
                        self._thread and self._thread.is_alive()
                    ),
                )
                return False
        _debug_event("pairing_receiver_ready", confirmed=True)
        return True

    def drain_replayed(
        self,
        *,
        quiet_period: float = 1.5,
        max_wait: float = 10.0,
        process_alive: Callable[[], bool] | None = None,
    ) -> int:
        self.start()
        clock = __import__("time")
        started = clock.monotonic()
        quiet_deadline = started + max(0.1, quiet_period)
        final_deadline = started + max(quiet_period, max_wait)
        discarded = 0

        while True:
            if process_alive is not None and not process_alive():
                return discarded

            try:
                error = self.errors.get_nowait()
            except queue.Empty:
                pass
            else:
                raise RuntimeError(
                    f"Rust+ notification listener failed: {error}"
                ) from error

            now = clock.monotonic()
            if now >= quiet_deadline or now >= final_deadline:
                _debug_event(
                    "pairing_stale_drain_completed",
                    discarded=discarded,
                    duration_ms=round((now - started) * 1000, 2),
                    quiet_period=quiet_period,
                    max_wait=max_wait,
                )
                return discarded

            timeout = max(
                0.01,
                min(
                    0.25,
                    quiet_deadline - now,
                    final_deadline - now,
                ),
            )
            try:
                record = self.records.get(timeout=timeout)
            except queue.Empty:
                continue

            discarded += 1
            quiet_deadline = min(
                final_deadline,
                clock.monotonic() + max(0.1, quiet_period),
            )
            print(
                "[FRESHNESS GATE] Discarded queued pairing data for "
                f"{record.server_name or record.host or 'an earlier request'}."
            )

    def wait_for(
        self,
        host: str,
        *,
        timeout: float | None = None,
        process_alive: Callable[[], bool] | None = None,
    ) -> PairingRecord | None:
        self.start()
        clock = __import__("time")
        deadline = None if timeout is None else clock.monotonic() + timeout
        aggregate: PairingRecord | None = None
        first_partial_at: float | None = None
        last_reminder_at = clock.monotonic()

        while True:
            if process_alive is not None and not process_alive():
                return None

            try:
                error = self.errors.get_nowait()
            except queue.Empty:
                pass
            else:
                raise RuntimeError(
                    f"Rust+ notification listener failed: {error}"
                ) from error

            remaining = 1.0
            if deadline is not None:
                remaining = max(
                    0.0,
                    min(1.0, deadline - clock.monotonic()),
                )
                if remaining <= 0:
                    return None

            try:
                record = self.records.get(timeout=remaining)
            except queue.Empty:
                now = clock.monotonic()
                if (
                    aggregate is not None
                    and not aggregate.is_complete()
                    and now - last_reminder_at >= 20.0
                ):
                    elapsed = int(now - (first_partial_at or now))
                    print(
                        "[RUST+ PUSH] Pairing request is still active "
                        f"after {elapsed}s; waiting for the final player token."
                    )
                    print(
                        "[RUST+ PUSH] Keep the receiver open. If Rust offers "
                        "Retry/Resend, use it once without unpairing the phone."
                    )
                    last_reminder_at = now
                continue

            if (
                aggregate is not None
                and aggregate.steam_id
                and record.steam_id
                and aggregate.steam_id != record.steam_id
            ):
                print(
                    "[RUST+ PUSH] Ignored a fresh notification for a "
                    "different Steam account."
                )
                _debug_event(
                    "pairing_record_ignored",
                    reason="different_steam_account",
                    host=record.host,
                    server_name=record.server_name,
                )
                continue

            if _is_conflicting_delayed_authorization(aggregate, record):
                print(
                    "[RUST+ PUSH] Ignored a delayed authorization for "
                    f"{record.server_name or record.host}; it conflicts "
                    "with the active fresh pairing request."
                )
                _debug_event(
                    "pairing_record_ignored",
                    reason="conflicting_delayed_authorization",
                    active_host=aggregate.host if aggregate else "",
                    active_server=aggregate.server_name if aggregate else "",
                    incoming_host=record.host,
                    incoming_server=record.server_name,
                )
                continue

            if (
                aggregate is not None
                and aggregate.host
                and record.host
                and not aggregate.matches_host(record.host)
                and not record.player_token
            ):
                print(
                    "[RUST+ PUSH] A newer server pairing request replaced "
                    "the previous incomplete handshake."
                )
                aggregate = None
                first_partial_at = None

            aggregate = _merge_pairing_records(aggregate, record)

            if aggregate.is_complete():
                _debug_event(
                    "pairing_handshake_complete",
                    host=aggregate.host,
                    port=aggregate.port,
                    player_token_sign=(
                        "negative"
                        if aggregate.player_token < 0
                        else "positive"
                    ),
                    server_name=aggregate.server_name,
                )
                if host and aggregate.host and not aggregate.matches_host(host):
                    print(
                        "[RUST+ PUSH] Companion endpoint "
                        f"{aggregate.host}:{aggregate.port} differs from "
                        f"game endpoint {host}; forwarding it for live "
                        "Rust+ validation."
                    )
                return aggregate

            if first_partial_at is None:
                first_partial_at = clock.monotonic()

            missing = ", ".join(_pairing_missing_fields(aggregate))
            endpoint = f"{aggregate.host or '?'}:{aggregate.port or '?'}"
            _debug_event(
                "pairing_handshake_partial",
                host=aggregate.host,
                port=aggregate.port,
                missing=missing,
                server_name=aggregate.server_name,
            )
            print(
                "[RUST+ PUSH] Pairing handshake started for "
                f"{aggregate.server_name or endpoint}; still missing {missing}."
            )
            print(
                "[RUST+ PUSH] Keep the receiver open while completing the "
                "phone confirmation. Later pushes are merged automatically."
            )






def _safe_payload_inventory(
    value: Any,
    *,
    limit: int = 180,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sensitive_fragments = (
        "token",
        "auth",
        "password",
        "cookie",
        "secret",
        "credential",
        "session",
    )
    known_fields = {
        "ip",
        "host",
        "serverip",
        "server_ip",
        "address",
        "port",
        "appport",
        "app_port",
        "app.port",
        "rustappport",
        "rust_app_port",
        "companionport",
        "companion_port",
        "name",
        "servername",
        "server_name",
        "playerid",
        "player_id",
        "steamid",
        "steam_id",
        "playertoken",
        "player_token",
    }
    seen: set[int] = set()

    def walk(child: Any, path: str, depth: int) -> None:
        if len(rows) >= limit or depth > 12:
            return

        if isinstance(child, (dict, list, tuple)) or hasattr(child, "__dict__"):
            identity = id(child)
            if identity in seen:
                rows.append(
                    {
                        "path": path,
                        "type": type(child).__name__,
                        "cycle": True,
                    }
                )
                return
            seen.add(identity)

        if isinstance(child, dict):
            rows.append(
                {
                    "path": path,
                    "type": "dict",
                    "keys": sorted(str(key) for key in child.keys())[:80],
                    "length": len(child),
                }
            )
            for key, nested in child.items():
                walk(nested, f"{path}.{key}", depth + 1)
            return

        if isinstance(child, (list, tuple)):
            rows.append(
                {
                    "path": path,
                    "type": type(child).__name__,
                    "length": len(child),
                }
            )
            for index, nested in enumerate(child[:40]):
                walk(nested, f"{path}[{index}]", depth + 1)
            return

        if isinstance(child, (bytes, bytearray)):
            child = bytes(child).decode("utf-8", errors="replace")

        if isinstance(child, str):
            text = child.strip()
            leaf = path.rsplit(".", 1)[-1].casefold()
            normalized_leaf = _normalize_key(leaf)
            sensitive = any(fragment in leaf for fragment in sensitive_fragments)
            row: dict[str, Any] = {
                "path": path,
                "type": "str",
                "length": len(child),
                "sensitive": sensitive,
                "digit_count": sum(character.isdigit() for character in text),
            }
            if normalized_leaf in known_fields:
                if sensitive or "token" in normalized_leaf:
                    row["value"] = "<present>" if text else "<empty>"
                elif normalized_leaf in {
                    "playerid",
                    "player_id",
                    "steamid",
                    "steam_id",
                }:
                    row["value"] = f"...{text[-6:]}" if text else "<empty>"
                else:
                    row["value"] = text[:180]

            decoded = None
            if (
                (text.startswith("{") and text.endswith("}"))
                or (text.startswith("[") and text.endswith("]"))
            ):
                try:
                    decoded = json.loads(text)
                except json.JSONDecodeError:
                    row["json_error"] = True
                else:
                    row["json_decoded"] = True
                    row["json_type"] = type(decoded).__name__
            else:
                names = re.findall(
                    r"[\"']([A-Za-z0-9_.-]{1,80})[\"']\s*:",
                    text,
                )
                if names:
                    row["embedded_field_names"] = sorted(set(names))[:80]

            rows.append(row)
            if decoded is not None:
                walk(decoded, f"{path}<json>", depth + 1)
            return

        leaf = path.rsplit(".", 1)[-1].casefold()
        sensitive = any(fragment in leaf for fragment in sensitive_fragments)
        row = {
            "path": path,
            "type": type(child).__name__,
            "sensitive": sensitive,
        }
        if isinstance(child, (int, float, bool)) or child is None:
            normalized_leaf = _normalize_key(leaf)
            if sensitive or "token" in normalized_leaf:
                row["value"] = "<present>" if child else "<empty>"
            elif normalized_leaf in known_fields:
                value_text = str(child)
                if normalized_leaf in {
                    "playerid",
                    "player_id",
                    "steamid",
                    "steam_id",
                }:
                    row["value"] = f"...{value_text[-6:]}" if value_text else "<empty>"
                else:
                    row["value"] = child
        rows.append(row)

        if hasattr(child, "__dict__"):
            try:
                walk(vars(child), f"{path}<vars>", depth + 1)
            except TypeError:
                pass

    walk(value, "$", 0)
    return rows


def _append_payload_diagnostic(
    notification: Any,
    data_message: Any,
    obj: Any,
) -> None:
    debug_dir = APP_DATA_DIR / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / "pairing-payload-structure.jsonl"

    if path.is_file() and path.stat().st_size > 1_500_000:
        try:
            retained = path.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()[-80:]
            path.write_text(
                "\n".join(retained) + ("\n" if retained else ""),
                encoding="utf-8",
                newline="\n",
            )
        except OSError:
            pass

    datetime_module = __import__("datetime")
    payload = {
        "captured_at": datetime_module.datetime.now(
            datetime_module.timezone.utc
        ).isoformat(timespec="milliseconds"),
        "notification": _safe_payload_inventory(notification),
        "data_message": _safe_payload_inventory(data_message),
        "object": _safe_payload_inventory(obj),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(payload, ensure_ascii=False, sort_keys=True)
            + "\n"
        )


def save_fcm_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(config, indent=2), encoding="utf-8")
    temporary.replace(path)


def _walk_mappings(
    value: Any,
    *,
    _depth: int = 0,
    _seen: set[int] | None = None,
):
    if _depth > 14:
        return
    if _seen is None:
        _seen = set()

    track_identity = (
        isinstance(value, (dict, list, tuple))
        or hasattr(value, "__dict__")
        or hasattr(value, "app_data")
    )
    if track_identity:
        identity = id(value)
        if identity in _seen:
            return
        _seen.add(identity)

    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mappings(
                child,
                _depth=_depth + 1,
                _seen=_seen,
            )
        return

    if isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mappings(
                child,
                _depth=_depth + 1,
                _seen=_seen,
            )
        return

    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8", errors="replace")

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return
        if (
            (text.startswith("{") and text.endswith("}"))
            or (text.startswith("[") and text.endswith("]"))
        ):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                decoded = None
            if decoded is not None:
                yield from _walk_mappings(
                    decoded,
                    _depth=_depth + 1,
                    _seen=_seen,
                )
                return
        decoded_url = _payload_from_url(text)
        if decoded_url:
            yield from _walk_mappings(
                decoded_url,
                _depth=_depth + 1,
                _seen=_seen,
            )
        return

    if hasattr(value, "app_data"):
        normalized = _coerce_data_message_mapping(value)
        if normalized:
            yield from _walk_mappings(
                normalized,
                _depth=_depth + 1,
                _seen=_seen,
            )

    if hasattr(value, "__dict__"):
        try:
            attributes = vars(value)
        except TypeError:
            return
        yield from _walk_mappings(
            attributes,
            _depth=_depth + 1,
            _seen=_seen,
        )




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


def _first_text(
    mapping: dict[str, Any],
    keys: Any,
) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value).strip().strip("[]")
    return ""



def _first_int(
    mapping: dict[str, Any],
    keys: Any,
) -> int:
    for key in keys:
        value = mapping.get(key)
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 0
