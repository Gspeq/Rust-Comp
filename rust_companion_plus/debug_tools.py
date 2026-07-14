from __future__ import annotations
import ast

import argparse
import atexit
import functools
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rust_companion_plus.config import APP_DATA_DIR, STORE_PATH, FCM_CONFIG_PATH


_DEBUG_DIR = APP_DATA_DIR / "debug"
_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = threading.Lock()
_SESSION_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
_LOG_PATH = _DEBUG_DIR / f"diagnostics-{_SESSION_ID}.jsonl"
_LATEST_POINTER = _DEBUG_DIR / "latest-debug-log.txt"
_INSTALLED = False

_SECRET_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "authorization",
    "auth",
    "fcm",
    "expo",
    "cookie",
    "sessionid",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _is_secret_key(key: Any) -> bool:
    normalized = str(key).casefold().replace("-", "").replace("_", "")
    return any(fragment in normalized for fragment in _SECRET_FRAGMENTS)


def _redact(
    value: Any,
    *,
    key: str = "",
    depth: int = 0,
) -> Any:
    if key and _is_secret_key(key):
        normalized_key = (
            str(key).casefold().replace("-", "").replace("_", "")
        )
        if isinstance(value, bool) or normalized_key.endswith("present"):
            return bool(value)
        if normalized_key.endswith("sign") and value in {
            "positive",
            "negative",
            "missing",
            "zero",
        }:
            return value
        if value in (None, "", 0, False):
            return value
        return "<redacted>"

    if depth >= 6:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for child_key, child in list(value.items())[:100]:
            result[str(child_key)] = _redact(
                child,
                key=str(child_key),
                depth=depth + 1,
            )
        if len(value) > 100:
            result["<truncated>"] = len(value) - 100
        return result
    if isinstance(value, (list, tuple, set)):
        rows = list(value)
        result = [_redact(child, depth=depth + 1) for child in rows[:100]]
        if len(rows) > 100:
            result.append(f"<{len(rows) - 100} more>")
        return result
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<bytes:{len(value)}>"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return f"<{type(value).__module__}.{type(value).__name__}>"



def _shape(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "None"}
    if isinstance(value, dict):
        return {
            "type": "dict",
            "keys": sorted(str(key) for key in value.keys())[:60],
            "length": len(value),
        }
    if isinstance(value, (list, tuple, set)):
        return {"type": type(value).__name__, "length": len(value)}
    if isinstance(value, (bytes, bytearray)):
        return {"type": type(value).__name__, "length": len(value)}
    if isinstance(value, str):
        return {"type": "str", "length": len(value)}
    if hasattr(value, "__dict__"):
        try:
            keys = sorted(str(key) for key in vars(value).keys())[:60]
        except Exception:
            keys = []
        return {
            "type": f"{type(value).__module__}.{type(value).__name__}",
            "keys": keys,
        }
    return {"type": f"{type(value).__module__}.{type(value).__name__}"}


def _record_summary(
    record: Any,
) -> dict[str, Any] | None:
    if record is None:
        return None
    steam_id = int(getattr(record, "steam_id", 0) or 0)
    player_token = int(getattr(record, "player_token", 0) or 0)
    return {
        "host": str(getattr(record, "host", "") or ""),
        "port": int(getattr(record, "port", 0) or 0),
        "steam_suffix": str(steam_id)[-6:] if steam_id else "",
        "steam_present": bool(steam_id),
        "player_token_present": bool(player_token),
        "player_token_sign": (
            "negative"
            if player_token < 0
            else "positive"
            if player_token > 0
            else "missing"
        ),
        "server_name": str(getattr(record, "server_name", "") or ""),
        "source": str(getattr(record, "source", "") or ""),
        "complete": bool(getattr(record, "is_complete", lambda: False)()),
    }



def _credentials_summary(
    credentials: Any,
) -> dict[str, Any]:
    steam_id = int(getattr(credentials, "steam_id", 0) or 0)
    player_token = int(getattr(credentials, "player_token", 0) or 0)
    return {
        "host": str(getattr(credentials, "host", "") or ""),
        "port": int(getattr(credentials, "port", 0) or 0),
        "steam_suffix": str(steam_id)[-6:] if steam_id else "",
        "steam_present": bool(steam_id),
        "player_token_present": bool(player_token),
        "player_token_sign": (
            "negative"
            if player_token < 0
            else "positive"
            if player_token > 0
            else "missing"
        ),
        "complete": bool(
            getattr(credentials, "is_complete", lambda: False)()
        ),
    }



def _report_summary(report: Any) -> dict[str, Any]:
    selected = getattr(report, "selected", None)
    battlemetrics = getattr(report, "battlemetrics", {}) or {}
    return {
        "selected_host": str(getattr(selected, "host", "") or ""),
        "selected_port": int(getattr(selected, "port", 0) or 0),
        "selected_source": str(getattr(selected, "source", "") or ""),
        "selected_confidence": float(getattr(selected, "confidence", 0.0) or 0.0),
        "selected_observed_at": str(getattr(selected, "observed_at", "") or ""),
        "rust_app_port": int(getattr(report, "rust_app_port", 0) or 0),
        "rust_app_port_source": str(
            getattr(report, "rust_app_port_source", "") or ""
        ),
        "battlemetrics_id": str(battlemetrics.get("id") or ""),
        "battlemetrics_name": str(battlemetrics.get("name") or ""),
        "warnings": list(getattr(report, "warnings", []) or []),
        "log_path": str(getattr(report, "log_path", "") or ""),
    }


def event(name: str, **fields: Any) -> None:
    row = {
        "timestamp": _utc_now(),
        "session_id": _SESSION_ID,
        "event": name,
        **_redact(fields),
    }
    serialized = json.dumps(row, ensure_ascii=False, sort_keys=True)
    with _LOCK:
        with _LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")
        _LATEST_POINTER.write_text(str(_LOG_PATH), encoding="utf-8")

    if os.environ.get("RUST_COMPANION_DEBUG_CONSOLE", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        brief = {
            key: value
            for key, value in row.items()
            if key not in {"timestamp", "session_id"}
        }
        print(f"[DEBUG] {json.dumps(brief, ensure_ascii=False, sort_keys=True)}")


def _git_text(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception as exc:
        return f"<git unavailable: {exc}>"
    output = (result.stdout or result.stderr).strip()
    return output


def _wrap_function(owner: Any, name: str, wrapper_factory: Any) -> None:
    original = getattr(owner, name, None)
    if original is None or getattr(original, "_rust_companion_debug_wrapped", False):
        return
    wrapped = wrapper_factory(original)
    setattr(wrapped, "_rust_companion_debug_wrapped", True)
    setattr(owner, name, wrapped)


def install_debug_runtime(bootstrap_module: Any) -> Path:
    global _INSTALLED
    if _INSTALLED:
        return _LOG_PATH
    _INSTALLED = True

    from rust_companion_plus.services import pairing as pairing_module
    from rust_companion_plus.services import rustplus_client as rustplus_module

    event(
        "debug_session_started",
        pid=os.getpid(),
        parent_pid=os.getppid(),
        python=sys.version,
        executable=sys.executable,
        argv=sys.argv,
        cwd=str(Path.cwd()),
        platform=platform.platform(),
        frozen=bool(getattr(sys, "frozen", False)),
        git_branch=_git_text("branch", "--show-current"),
        git_head=_git_text("rev-parse", "--short", "HEAD"),
        git_status=_git_text("status", "--short"),
        log_path=str(_LOG_PATH),
    )
    print(f"[DEBUG] Development diagnostics enabled: {_LOG_PATH}")

    original_excepthook = sys.excepthook

    def debug_excepthook(exc_type: Any, exc: BaseException, tb: Any) -> None:
        event(
            "unhandled_exception",
            exception_type=getattr(exc_type, "__name__", str(exc_type)),
            message=str(exc),
            traceback="".join(traceback.format_exception(exc_type, exc, tb)),
        )
        original_excepthook(exc_type, exc, tb)

    sys.excepthook = debug_excepthook

    def parse_wrapper(original: Any) -> Any:
        @functools.wraps(original)
        def wrapped(value: Any, *args: Any, **kwargs: Any) -> Any:
            source = str(kwargs.get("source", "") or "")
            event(
                "pairing_parse_started",
                source=source,
                payload_shape=_shape(value),
            )
            started = time.monotonic()
            try:
                record = original(value, *args, **kwargs)
            except Exception as exc:
                event(
                    "pairing_parse_failed",
                    source=source,
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                )
                raise
            event(
                "pairing_parse_completed",
                source=source,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                record=_record_summary(record),
            )
            return record

        return wrapped

    _wrap_function(pairing_module, "parse_pairing_payload", parse_wrapper)
    bootstrap_module.parse_pairing_payload = pairing_module.parse_pairing_payload

    def start_wrapper(original: Any) -> Any:
        @functools.wraps(original)
        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            event(
                "pairing_receiver_start",
                already_started=bool(getattr(self, "_started", False)),
                record_queue_size=getattr(getattr(self, "records", None), "qsize", lambda: -1)(),
                error_queue_size=getattr(getattr(self, "errors", None), "qsize", lambda: -1)(),
                config_shape=_shape(getattr(self, "fcm_config", None)),
            )
            try:
                result = original(self, *args, **kwargs)
            except Exception as exc:
                event(
                    "pairing_receiver_start_failed",
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                )
                raise
            event(
                "pairing_receiver_started",
                started=bool(getattr(self, "_started", False)),
                listener_type=type(getattr(self, "_listener", None)).__name__,
            )
            return result

        return wrapped

    _wrap_function(pairing_module.PairingNotificationInbox, "start", start_wrapper)

    def wait_wrapper(original: Any) -> Any:
        @functools.wraps(original)
        def wrapped(self: Any, host: str, *args: Any, **kwargs: Any) -> Any:
            event(
                "pairing_wait_started",
                expected_host=host,
                timeout=kwargs.get("timeout"),
                record_queue_size=getattr(self.records, "qsize", lambda: -1)(),
                error_queue_size=getattr(self.errors, "qsize", lambda: -1)(),
            )
            started = time.monotonic()
            try:
                record = original(self, host, *args, **kwargs)
            except Exception as exc:
                event(
                    "pairing_wait_failed",
                    expected_host=host,
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                )
                raise
            event(
                "pairing_wait_completed",
                expected_host=host,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                record=_record_summary(record),
                record_queue_size=getattr(self.records, "qsize", lambda: -1)(),
            )
            return record

        return wrapped

    _wrap_function(pairing_module.PairingNotificationInbox, "wait_for", wait_wrapper)

    def snapshot_wrapper(original: Any) -> Any:
        @functools.wraps(original)
        def wrapped(self: Any, credentials: Any, *args: Any, **kwargs: Any) -> Any:
            event(
                "rustplus_validation_started",
                credentials=_credentials_summary(credentials),
            )
            started = time.monotonic()
            try:
                snapshot = original(self, credentials, *args, **kwargs)
            except Exception as exc:
                event(
                    "rustplus_validation_failed",
                    credentials=_credentials_summary(credentials),
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                )
                raise
            server = getattr(snapshot, "server", {}) or {}
            event(
                "rustplus_validation_succeeded",
                credentials=_credentials_summary(credentials),
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                server_name=str(server.get("name") or ""),
                server_url=str(server.get("url") or ""),
                team_count=len(getattr(snapshot, "team", []) or []),
                marker_count=len(getattr(snapshot, "markers", []) or []),
            )
            return snapshot

        return wrapped

    _wrap_function(rustplus_module.RustPlusClient, "fetch_snapshot", snapshot_wrapper)
    bootstrap_module.RustPlusClient = rustplus_module.RustPlusClient

    def server_wait_wrapper(original: Any) -> Any:
        @functools.wraps(original)
        def wrapped(store: Any, *args: Any, **kwargs: Any) -> Any:
            event("server_detection_wait_started")
            started = time.monotonic()
            try:
                report = original(store, *args, **kwargs)
            except Exception as exc:
                event(
                    "server_detection_wait_failed",
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                )
                raise
            event(
                "server_detection_locked",
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                report=_report_summary(report),
            )
            return report

        return wrapped

    _wrap_function(bootstrap_module, "wait_for_server", server_wait_wrapper)

    def save_profile_wrapper(original: Any) -> Any:
        @functools.wraps(original)
        def wrapped(
            store: Any,
            key: str,
            current: Any,
            report: Any,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            event(
                "profile_save_started",
                profile_key=key,
                credentials=_credentials_summary(current),
                pairing_source=str(kwargs.get("pairing_source", "") or ""),
                report=_report_summary(report),
            )
            result = original(
                store,
                key,
                current,
                report,
                *args,
                **kwargs,
            )
            event(
                "profile_save_completed",
                profile_key=key,
                credentials=_credentials_summary(current),
            )
            return result

        return wrapped

    _wrap_function(bootstrap_module, "_save_profile", save_profile_wrapper)

    def listen_wrapper(original: Any) -> Any:
        @functools.wraps(original)
        def wrapped(
            current: Any,
            expected_host: str,
            finder: Any,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            event(
                "pairing_flow_started",
                expected_game_host=expected_host,
                credentials_before=_credentials_summary(current),
            )
            started = time.monotonic()
            try:
                source = original(
                    current,
                    expected_host,
                    finder,
                    *args,
                    **kwargs,
                )
            except Exception as exc:
                event(
                    "pairing_flow_failed",
                    expected_game_host=expected_host,
                    credentials=_credentials_summary(current),
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                )
                raise
            event(
                "pairing_flow_completed",
                expected_game_host=expected_host,
                credentials_after=_credentials_summary(current),
                pairing_source=str(source or ""),
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
            return source

        return wrapped

    _wrap_function(bootstrap_module, "_listen_for_pairing", listen_wrapper)

    def validate_wrapper(original: Any) -> Any:
        @functools.wraps(original)
        def wrapped(
            store: Any,
            report: Any,
            key: str,
            current: Any,
            pairing_source: str,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            event(
                "validation_flow_started",
                profile_key=key,
                pairing_source=pairing_source,
                credentials=_credentials_summary(current),
                report=_report_summary(report),
            )
            try:
                snapshot = original(
                    store,
                    report,
                    key,
                    current,
                    pairing_source,
                    *args,
                    **kwargs,
                )
            except Exception as exc:
                event(
                    "validation_flow_failed",
                    profile_key=key,
                    credentials=_credentials_summary(current),
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                )
                raise
            event(
                "validation_flow_completed",
                profile_key=key,
                credentials=_credentials_summary(current),
            )
            return snapshot

        return wrapped

    _wrap_function(bootstrap_module, "_validate_profile", validate_wrapper)

    atexit.register(lambda: event("debug_session_finished"))
    return _LOG_PATH


def _latest_log() -> Path | None:
    try:
        path = Path(_LATEST_POINTER.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rust_log_path() -> Path:
    override = os.environ.get("RUST_LOG_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(
        r"C:\Program Files (x86)\Steam\steamapps\common\Rust\output_log.txt"
    )


def create_debug_bundle(output_path: Path | None = None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"rust-companion-debug-{timestamp}.zip"

    if output_path is None:
        output_path = Path.cwd() / "debug_bundles" / filename
    else:
        output_path = output_path.expanduser()
        if output_path.suffix.casefold() != ".zip":
            output_path = output_path / filename

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    environment = {
        "created_at": _utc_now(),
        "python": sys.version,
        "executable": sys.executable,
        "argv": sys.argv,
        "cwd": str(Path.cwd()),
        "platform": platform.platform(),
        "git_branch": _git_text("branch", "--show-current"),
        "git_head": _git_text("rev-parse", "--short", "HEAD"),
        "git_status": _git_text("status", "--short"),
        "git_diff_check": _git_text("diff", "--check"),
    }

    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "environment.json",
            json.dumps(_redact(environment), indent=2, ensure_ascii=False),
        )

        latest = _latest_log()
        if latest is not None:
            archive.write(latest, f"diagnostics/{latest.name}")

        for log in sorted(_DEBUG_DIR.glob("diagnostics-*.jsonl"))[-5:]:
            if latest is not None and log == latest:
                continue
            archive.write(log, f"diagnostics/{log.name}")

        if STORE_PATH.is_file():
            try:
                store = json.loads(
                    STORE_PATH.read_text(encoding="utf-8-sig")
                )
            except Exception as exc:
                archive.writestr("store-read-error.txt", str(exc))
            else:
                archive.writestr(
                    "store-redacted.json",
                    json.dumps(
                        _redact(store),
                        indent=2,
                        ensure_ascii=False,
                    ),
                )

        rust_log = _rust_log_path()
        if rust_log.is_file():
            try:
                lines = rust_log.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).splitlines()
                archive.writestr(
                    "rust-output-log-tail.txt",
                    "\n".join(lines[-700:]) + "\n",
                )
            except Exception as exc:
                archive.writestr("rust-log-read-error.txt", str(exc))

        source_rows: dict[str, Any] = {}
        repo = Path.cwd()
        for relative in (
            "rust_companion_plus/bootstrap.py",
            "rust_companion_plus/services/pairing.py",
            "rust_companion_plus/services/fcm_registration.py",
            "rust_companion_plus/services/rustplus_client.py",
            "rust_companion_plus/services/server_profiles.py",
            "rust_companion_plus/app.py",
            "rust_companion_plus/ui/tabs/map_tab.py",
        "rust_companion_plus/services/server_profiles.py",
        "rust_companion_plus/app.py",
        "rust_companion_plus/ui/tabs/map_tab.py",
        "rust_companion_plus/services/item_catalog.py",
        "rust_companion_plus/ui/tabs/shops.py",
            "rust_companion_plus/services/item_catalog.py",
            "rust_companion_plus/ui/tabs/shops.py",
            "rust_companion_plus/debug_tools.py",
        ):
            path = repo / relative
            if path.is_file():
                source_rows[relative] = {
                    "sha256": _file_digest(path),
                    "size": path.stat().st_size,
                    "modified": datetime.fromtimestamp(
                        path.stat().st_mtime,
                        timezone.utc,
                    ).isoformat(),
                }
        archive.writestr(
            "source-manifest.json",
            json.dumps(source_rows, indent=2),
        )

    pointer = output_path.parent / "latest-debug-bundle.txt"
    pointer.write_text(str(output_path), encoding="utf-8")
    print(f"Debug bundle created: {output_path}")
    print(f"DEBUG_BUNDLE_PATH={output_path}")
    return output_path





def _saved_profile_summary(
    store: dict[str, Any],
) -> list[dict[str, Any]]:
    raw = store.get("saved_server_profiles", {})
    if not isinstance(raw, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        snapshot = (
            value.get("snapshot")
            if isinstance(value.get("snapshot"), dict)
            else {}
        )
        team = snapshot.get("team")
        markers = snapshot.get("markers")
        assets = (
            value.get("assets")
            if isinstance(value.get("assets"), dict)
            else {}
        )
        rows.append(
            {
                "key": str(key),
                "name": value.get("name", ""),
                "game_endpoint": value.get(
                    "game_endpoint",
                    "",
                ),
                "rustplus_endpoint": value.get(
                    "rustplus_endpoint",
                    "",
                ),
                "saved_at": value.get("saved_at", ""),
                "live_updated_at": value.get(
                    "live_updated_at",
                    "",
                ),
                "team_members": (
                    len(team)
                    if isinstance(team, list)
                    else 0
                ),
                "markers": (
                    len(markers)
                    if isinstance(markers, list)
                    else 0
                ),
                "has_map_image": bool(
                    assets.get("map_image_path")
                ),
                "has_parsed_map": bool(
                    assets.get("parsed_map_dir")
                ),
                "has_raw_map": bool(
                    assets.get("raw_map_path")
                ),
                "map_url_present": bool(
                    assets.get("map_url")
                ),
            }
        )
    rows.sort(
        key=lambda row: str(
            row.get("live_updated_at")
            or row.get("saved_at")
            or ""
        ),
        reverse=True,
    )
    return rows

def create_review_report(
    output_path: Path | None = None,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"rust-companion-review-{timestamp}.txt"

    if output_path is None:
        output_path = (
            Path.cwd()
            / "debug_bundles"
            / filename
        )
    else:
        output_path = output_path.expanduser()
        if output_path.suffix.casefold() != ".txt":
            output_path = output_path / filename

    output_path = output_path.resolve()
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    sections: list[str] = []

    def section(title: str, value: Any) -> None:
        if not isinstance(value, str):
            value = json.dumps(
                _redact(value),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        sections.extend(
            (
                "=" * 88,
                title,
                "=" * 88,
                value.rstrip(),
                "",
            )
        )

    raw_status = _git_text("status", "--short")
    status_lines = [
        line
        for line in raw_status.splitlines()
        if not any(
            fragment in line
            for fragment in (
                ".bak",
                "debug_bundles/",
                "debug_bundles\\",
                "release/",
                "release\\",
                "__pycache__",
            )
        )
    ]
    section(
        "BUILD / BRANCH STATE",
        {
            "created_at": _utc_now(),
            "python": sys.version,
            "platform": platform.platform(),
            "git_branch": _git_text(
                "branch",
                "--show-current",
            ),
            "git_head": _git_text(
                "rev-parse",
                "--short",
                "HEAD",
            ),
            "origin_test_live_sync": _git_text(
                "rev-parse",
                "--short",
                "origin/test-live-sync",
            ),
            "ahead_behind": _git_text(
                "rev-list",
                "--left-right",
                "--count",
                "HEAD...origin/test-live-sync",
            ),
            "relevant_git_status": "\n".join(
                status_lines
            ),
            "git_diff_check": _git_text(
                "diff",
                "--check",
            ),
        },
    )

    latest = _latest_log()
    timeline: list[str] = []
    if latest is not None:
        try:
            for line in latest.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()[-800:]:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_name = str(
                    row.get("event", "")
                ).casefold()
                if any(
                    marker in event_name
                    for marker in (
                        "server_detection",
                        "pairing",
                        "validation",
                        "profile",
                        "exception",
                        "debug_session",
                    )
                ):
                    timeline.append(
                        json.dumps(
                            _redact(row),
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
        except Exception as exc:
            timeline = [
                f"<diagnostics read failed: {exc}>"
            ]
    section(
        "PAIRING STATE-MACHINE TIMELINE",
        "\n".join(timeline[-320:])
        or "<no relevant debug events>",
    )

    payload_path = (
        APP_DATA_DIR
        / "debug"
        / "pairing-payload-structure.jsonl"
    )
    if payload_path.is_file():
        try:
            payload_rows = payload_path.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()[-12:]
            payload_text = "\n".join(payload_rows)
        except Exception as exc:
            payload_text = (
                f"<payload structure read failed: {exc}>"
            )
    else:
        payload_text = (
            "<no safe payload trace yet; reproduce one "
            "pairing attempt>"
        )
    section(
        "SAFE PAIRING PAYLOAD STRUCTURE / FCM APP_DATA",
        payload_text,
    )

    test_status_path = (
        APP_DATA_DIR
        / "debug"
        / "last-test-run.json"
    )
    if test_status_path.is_file():
        try:
            test_status = json.loads(
                test_status_path.read_text(
                    encoding="utf-8-sig"
                )
            )
        except Exception as exc:
            test_status = {
                "read_error": str(exc)
            }
    else:
        test_status = {
            "status": "No completed hotfix test run recorded."
        }
    section("LAST HOTFIX TEST RESULT", test_status)

    fcm_summary: dict[str, Any] = {
        "config_path": str(FCM_CONFIG_PATH),
        "config_exists": FCM_CONFIG_PATH.is_file(),
    }
    if FCM_CONFIG_PATH.is_file():
        try:
            config = json.loads(
                FCM_CONFIG_PATH.read_text(
                    encoding="utf-8-sig"
                )
            )
            fcm_credentials = config.get(
                "fcm_credentials"
            )
            fcm_summary.update(
                {
                    "registered_by": config.get(
                        "registered_by",
                        "",
                    ),
                    "device_id": config.get(
                        "device_id",
                        "",
                    ),
                    "registered_at": config.get(
                        "registered_at",
                        "",
                    ),
                    "receiver_registration_mode": config.get(
                        "receiver_registration_mode",
                        "",
                    ),
                    "last_facepunch_refresh_status": config.get(
                        "last_facepunch_refresh_status",
                        "",
                    ),
                    "facepunch_registered": config.get(
                        "facepunch_registered",
                        "legacy/unknown",
                    ),
                    "last_facepunch_unregister": config.get(
                        "last_facepunch_unregister",
                        "",
                    ),
                    "last_facepunch_unregister_status": config.get(
                        "last_facepunch_unregister_status",
                        "",
                    ),
                    "has_fcm_credentials": isinstance(
                        fcm_credentials,
                        dict,
                    ),
                    "has_expo_push_token": bool(
                        config.get("expo_push_token")
                    ),
                    "has_rustplus_auth_token": bool(
                        config.get("rustplus_auth_token")
                    ),
                    "last_facepunch_refresh": config.get(
                        "last_facepunch_refresh",
                        "",
                    ),
                    "config_keys": sorted(config.keys()),
                    "modified_at": datetime.fromtimestamp(
                        FCM_CONFIG_PATH.stat().st_mtime,
                        timezone.utc,
                    ).isoformat(),
                }
            )
        except Exception as exc:
            fcm_summary["read_error"] = str(exc)
    section("FCM RECEIVER REGISTRATION", fcm_summary)

    if STORE_PATH.is_file():
        try:
            store = json.loads(
                STORE_PATH.read_text(
                    encoding="utf-8-sig"
                )
            )
        except Exception as exc:
            store = {"store_read_error": str(exc)}
    else:
        store = {}

    detection = (
        store.get("server_detection", {})
        if isinstance(store, dict)
        else {}
    )
    decision_trace = [
        line
        for line in detection.get("debug", [])
        if any(
            marker in str(line).casefold()
            for marker in (
                "selected ",
                "rust+",
                "a2s",
                "battlemetrics",
                "websocket",
                "official-default",
                "process socket",
            )
        )
    ]
    section(
        "NETWORK DISCOVERY DECISION",
        {
            "selected": detection.get("selected"),
            "rust_app_port": detection.get(
                "rust_app_port"
            ),
            "rust_app_port_source": detection.get(
                "rust_app_port_source"
            ),
            "warnings": detection.get("warnings", []),
            "decision_trace": decision_trace[-120:],
            "packet_capture_enabled": False,
            "strategy": (
                "Rust log game endpoint, exact BattleMetrics, "
                "A2S rules, one verified game-port+67 "
                "WebSocket probe, then authoritative pairing "
                "payload."
            ),
        },
    )

    profiles = (
        store.get("credential_profiles", {})
        if isinstance(store, dict)
        else {}
    )
    profile_metadata = (
        store.get(
            "credential_profile_metadata",
            {},
        )
        if isinstance(store, dict)
        else {}
    )
    section(
        "REDACTED SERVER PROFILE VAULT",
        {
            "player_identity": (
                store.get("player_identity", {})
                if isinstance(store, dict)
                else {}
            ),
            "credential_profiles": profiles,
            "credential_profile_metadata": (
                profile_metadata
            ),
            "saved_server_profiles": (
                _saved_profile_summary(store)
                if isinstance(store, dict)
                else []
            ),
            "active_server_profile_key": (
                store.get("active_server_profile_key", "")
                if isinstance(store, dict)
                else ""
            ),
            "signed_player_token_supported": True,
        },
    )

    rust_log = _rust_log_path()
    rust_rows: list[str] = []
    if rust_log.is_file():
        try:
            markers = (
                "Connecting:",
                "Rust+",
                "Regenerated Rust+ token",
                "SteamID:",
                "app.port",
                "companion",
                "Loading custom map",
                "Welcome",
                "Bienvenido",
            )
            rust_rows = [
                line
                for line in rust_log.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).splitlines()[-2200:]
                if any(
                    marker.casefold()
                    in line.casefold()
                    for marker in markers
                )
            ]
        except Exception as exc:
            rust_rows = [
                f"<Rust log read failed: {exc}>"
            ]
    else:
        rust_rows = [
            f"<Rust log not found at {rust_log}>"
        ]
    section(
        "PAIRING-RELEVANT RUST LOG LINES",
        "\n".join(rust_rows[-220:]),
    )

    source_manifest: dict[str, Any] = {}
    for relative in (
        "rust_companion_plus/models.py",
        "rust_companion_plus/bootstrap.py",
        "rust_companion_plus/services/pairing.py",
        "rust_companion_plus/services/fcm_registration.py",
        "rust_companion_plus/services/server_finder.py",
        "rust_companion_plus/services/rustplus_client.py",
        "rust_companion_plus/debug_tools.py",
    ):
        path = Path.cwd() / relative
        if path.is_file():
            source_manifest[relative] = {
                "sha256": _file_digest(path),
                "size": path.stat().st_size,
                "modified": datetime.fromtimestamp(
                    path.stat().st_mtime,
                    timezone.utc,
                ).isoformat(),
            }
    section("SOURCE MANIFEST", source_manifest)

    output_path.write_text(
        "\n".join(sections),
        encoding="utf-8",
        newline="\n",
    )
    pointer = (
        output_path.parent
        / "latest-review-report.txt"
    )
    pointer.write_text(
        str(output_path),
        encoding="utf-8",
    )
    print(f"Review report created: {output_path}")
    print(f"REVIEW_REPORT_PATH={output_path}")
    return output_path




def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", action="store_true")
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--open-folder", action="store_true")
    parser.add_argument("--print-latest", action="store_true")
    args = parser.parse_args(argv)

    output = Path(args.output).expanduser() if args.output else None

    if args.review:
        artifact = create_review_report(output)
        if args.open_folder and os.name == "nt":
            try:
                subprocess.Popen(
                    ["explorer.exe", f"/select,{artifact}"],
                    close_fds=True,
                )
            except Exception as exc:
                print(f"Could not open Explorer automatically: {exc}")
        return 0

    if args.bundle:
        artifact = create_debug_bundle(output)
        if args.open_folder and os.name == "nt":
            try:
                subprocess.Popen(
                    ["explorer.exe", f"/select,{artifact}"],
                    close_fds=True,
                )
            except Exception as exc:
                print(f"Could not open Explorer automatically: {exc}")
        return 0

    if args.print_latest:
        latest = _latest_log()
        print(latest or "")
        return 0

    parser.print_help()
    return 0




if __name__ == "__main__":
    raise SystemExit(main())
