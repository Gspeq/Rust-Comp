from __future__ import annotations
import queue

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from rust_companion_plus.config import APP_DATA_DIR, FCM_CONFIG_PATH
from rust_companion_plus.models import RustCredentials, normalize_player_token
from rust_companion_plus.services.pairing import (
    PairingNotificationInbox,
    PairingRecord,
    load_fcm_config,
    parse_pairing_payload,
    save_fcm_config,
)
from rust_companion_plus.services.fcm_registration import (
    FCMRegistrationError,
    refresh_fcm_registration,
    request_or_register_fcm_config,
    cleanup_lingering_fcm_registration,
    unregister_fcm_registration,
)
from rust_companion_plus.services.rustplus_client import RustPlusClient, ServerSnapshot
from rust_companion_plus.services.server_finder import DetectionReport, RustServerFinder
from rust_companion_plus.services.server_profiles import ServerProfileVault
from rust_companion_plus.storage import JsonStore


LAUNCHER_SETUP_VERSION = 3
RESET = "\033[0m"
BOLD = "\033[1m"
ORANGE = "\033[38;5;208m"
AMBER = "\033[38;5;214m"
YELLOW = "\033[38;5;220m"
GREEN = "\033[38;5;82m"
CYAN = "\033[38;5;51m"
RED = "\033[38;5;196m"
WHITE = "\033[97m"
GRAY = "\033[38;5;245m"

ASCII_LINES = (
    r"  ____  _   _ ____ _____    ____ ___  __  __ ____   _    _   _ ___ ___  _   _ _ ",
    r" |  _ \| | | / ___|_   _|  / ___/ _ \|  \/  |  _ \ / \  | \ | |_ _/ _ \| \ | | |",
    r" | |_) | | | \___ \ | |   | |  | | | | |\/| | |_) / _ \ |  \| || | | | |  \| | |",
    r" |  _ <| |_| |___) || |   | |__| |_| | |  | |  __/ ___ \| |\  || | |_| | |\  |_|",
    r" |_| \_\\___/|____/ |_|    \____\___/|_|  |_|_| /_/   \_\_| \_|___\___/|_| \_(_)",
)


def _enable_terminal_color() -> None:
    if os.name == "nt":
        os.system("")


def _paint(text: str, color: str = "", *, bold: bool = False) -> str:
    prefix = color + (BOLD if bold else "")
    return f"{prefix}{text}{RESET}" if prefix else text


def _rule(char: str = "=", width: int = 92, color: str = GRAY) -> None:
    print(_paint(char * width, color))


def print_header() -> None:
    _enable_terminal_color()
    os.system("cls" if os.name == "nt" else "clear")
    print()
    _rule("#", color=ORANGE)
    for line, color in zip(ASCII_LINES, (ORANGE, ORANGE, AMBER, YELLOW, YELLOW)):
        print(_paint(line, color, bold=True))
    print(_paint("                         Developed by Taylor Marshall", WHITE, bold=True))
    print(_paint("       LIVE SESSION GATE  //  SERVER PROFILE VAULT  //  RUST+ PAIRING CONTROL", CYAN))
    _rule("#", color=ORANGE)
    print()


def _print_setup_banner() -> None:
    print(_paint("+------------------------------------------------------------------------------------------+", ORANGE, bold=True))
    print(_paint("|                     COMPANION+ INITIALIZATION / INTEGRATION VAULT                       |", AMBER, bold=True))
    print(_paint("+------------------------------------------------------------------------------------------+", ORANGE, bold=True))
    print(_paint("|  [01] Persistent AppData vault          [ONLINE]                                         |", GREEN))
    print(_paint("|  [02] Public intelligence providers     [CHECKING]                                       |", YELLOW))
    print(_paint("|  [03] Live Rust process gate            [ARMED]                                          |", CYAN))
    print(_paint("|  [04] Per-server Rust+ profiles          [LOCKED UNTIL SERVER DETECTED]                    |", ORANGE))
    print(_paint("+------------------------------------------------------------------------------------------+", ORANGE, bold=True))
    print()
    print(_paint(f"Persistent data directory: {APP_DATA_DIR}", GRAY))
    print(_paint("API-key input is visible while typing. Saved values carry into future source and EXE runs.", GRAY))
    print()


def _visible_optional_value(label: str, existing: str) -> str:
    if existing:
        print(_paint(f"[LOADED] {label}: saved value ending in ...{existing[-4:]}", GREEN))
        return existing
    return input(_paint(f"> {label} (optional, visible input): ", AMBER)).strip()


def configure_first_run(store: JsonStore) -> None:
    version = int(store.get("launcher_setup_version", 0) or 0)
    keys = dict(store.get("api_keys", {}) or {})
    if version >= LAUNCHER_SETUP_VERSION:
        configured = [name for name in ("battlemetrics", "rustmaps") if keys.get(name)]
        if configured:
            print(_paint("[VAULT] Global API integrations loaded from persistent storage.", GREEN))
        else:
            print(_paint("[VAULT] Public/manual integration mode loaded; optional API keys were previously skipped.", GRAY))
        return

    _print_setup_banner()
    keys["battlemetrics"] = _visible_optional_value(
        "BattleMetrics API token", str(keys.get("battlemetrics", "") or "")
    )
    keys["rustmaps"] = _visible_optional_value(
        "RustMaps API key", str(keys.get("rustmaps", "") or "")
    )
    store.set("api_keys", keys)
    store.set("launcher_setup_complete", True)
    store.set("launcher_setup_version", LAUNCHER_SETUP_VERSION)
    print()
    print(_paint("[CONFIG SAVED] Global integrations now follow every server profile.", GREEN, bold=True))
    _rule("-", color=GRAY)


def _status_line(message: str, color: str = CYAN) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"{_paint('[' + timestamp + ']', GRAY)} {_paint(message, color)}")



def _saved_profile_time(record: dict[str, Any]) -> str:
    raw = str(
        record.get("live_updated_at")
        or record.get("saved_at")
        or ""
    )
    if not raw:
        return "unknown"
    return raw.replace("T", " ")[:19]


def _choose_saved_profile(
    vault: ServerProfileVault,
) -> str:
    while True:
        profiles = vault.list_profiles()
        print()
        _rule("=", color=CYAN)
        print(
            _paint(
                "SAVED SERVER PROFILES",
                CYAN,
                bold=True,
            )
        )
        if not profiles:
            print(
                _paint(
                    "No saved server profiles exist yet. "
                    "Run a live session and choose Yes when closing.",
                    YELLOW,
                )
            )
            _rule("=", color=CYAN)
            return ""

        for index, record in enumerate(
            profiles,
            start=1,
        ):
            name = str(
                record.get("name")
                or record.get("key")
                or "Unnamed server"
            )
            game_endpoint = str(
                record.get("game_endpoint")
                or record.get("key")
                or "?"
            )
            rustplus_endpoint = str(
                record.get("rustplus_endpoint") or "?"
            )
            summary = (
                record.get("summary")
                if isinstance(record.get("summary"), dict)
                else {}
            )
            print(
                _paint(
                    f"  [{index}] {name}",
                    WHITE,
                    bold=True,
                )
            )
            print(
                _paint(
                    "      "
                    f"Game {game_endpoint}  |  "
                    f"Rust+ {rustplus_endpoint}  |  "
                    f"Saved/live {_saved_profile_time(record)}",
                    GRAY,
                )
            )
            print(
                _paint(
                    "      "
                    f"Map {summary.get('map') or '?'}  |  "
                    f"Size {summary.get('world_size') or '?'}  |  "
                    f"Cached team {summary.get('team_members', 0)}  |  "
                    f"Markers {summary.get('markers', 0)}",
                    GRAY,
                )
            )

        print(_paint("  [B] Back", GRAY))
        _rule("=", color=CYAN)
        choice = input(
            _paint(
                "> Select a saved profile number or B: ",
                AMBER,
            )
        ).strip().casefold()
        if choice == "b":
            return ""
        try:
            index = int(choice)
        except ValueError:
            print(
                _paint(
                    "Enter a profile number or B.",
                    RED,
                )
            )
            continue
        if not 1 <= index <= len(profiles):
            print(
                _paint(
                    "That saved profile number does not exist.",
                    RED,
                )
            )
            continue
        return str(
            profiles[index - 1].get("key") or ""
        )


def choose_launch_mode(
    store: JsonStore,
) -> tuple[str, str]:
    vault = ServerProfileVault(store)
    while True:
        profiles = vault.list_profiles()
        print()
        print(
            _paint(
                "LAUNCH MODE",
                ORANGE,
                bold=True,
            )
        )
        print(
            "  [L] Live session — wait for Rust and detect "
            "the server you join"
        )
        saved_label = (
            f" — {len(profiles)} profile(s) available"
            if profiles
            else " — none saved yet"
        )
        print(
            "  [S] View saved server profile"
            f"{saved_label}"
        )
        print("  [Q] Quit")
        choice = input(
            _paint(
                "> Select L / S / Q: ",
                AMBER,
            )
        ).strip().casefold()

        if choice == "l":
            return "live", ""
        if choice == "q":
            return "quit", ""
        if choice == "s":
            key = _choose_saved_profile(vault)
            if key:
                return "saved", key
            continue
        print(
            _paint(
                "Choose L, S, or Q.",
                RED,
            )
        )

def wait_for_server(store: JsonStore) -> DetectionReport:
    finder = RustServerFinder(store)
    attempts = 0
    last_pids: tuple[int, ...] = ()
    stable_socket_endpoint = ""
    stable_socket_count = 0

    print(_paint("Thanks! Rust session watcher is online.", GREEN, bold=True))
    print(_paint("Launch Rust, then join a server. Closed-game and old-log sessions are rejected.", WHITE))
    _rule("-", color=GRAY)

    while True:
        attempts += 1
        session = finder.get_rust_process_session()
        if not session.running:
            last_pids = ()
            stable_socket_endpoint = ""
            stable_socket_count = 0
            if attempts == 1 or attempts % 5 == 0:
                _status_line("WAITING FOR RUSTCLIENT.EXE TO START", YELLOW)
            time.sleep(2)
            continue

        pids = tuple(session.pids)
        if pids != last_pids:
            last_pids = pids
            stable_socket_endpoint = ""
            stable_socket_count = 0
            _status_line(
                f"RUST PROCESS ONLINE  PID={','.join(map(str, pids))}  SESSION={session.started_at or 'unknown'}",
                GREEN,
            )
            _status_line("WAITING FOR A NEW SERVER CONNECTION FROM THIS RUST SESSION", CYAN)

        report = finder.detect_once(
            enrich=False,
            require_running_process=True,
            session_started_at=session.started_at_epoch,
            current_session_only=True,
        )
        selected = report.selected

        if selected is not None and selected.source.startswith("rust_log_"):
            enriched = finder.detect_once(
                enrich=True,
                require_running_process=True,
                session_started_at=session.started_at_epoch,
                current_session_only=True,
            )
            if enriched.selected and enriched.selected.endpoint == selected.endpoint:
                return enriched

        if selected is not None and selected.source == "rust_process_remote_socket":
            if selected.endpoint == stable_socket_endpoint:
                stable_socket_count += 1
            else:
                stable_socket_endpoint = selected.endpoint
                stable_socket_count = 1
            if stable_socket_count >= 3:
                enriched = finder.detect_once(
                    enrich=True,
                    require_running_process=True,
                    session_started_at=session.started_at_epoch,
                    current_session_only=True,
                )
                if enriched.selected and enriched.selected.endpoint == selected.endpoint:
                    enriched.warnings.append(
                        "Endpoint was confirmed through a stable Rust process socket because no current-session "
                        "Raknet connection line was available."
                    )
                    return enriched
        else:
            stable_socket_endpoint = ""
            stable_socket_count = 0

        if attempts == 1 or attempts % 5 == 0:
            status = report.debug[-1] if report.debug else "No current-session endpoint yet"
            _status_line(status.upper(), CYAN)
            if report.log_path:
                print(_paint(f"             Watching: {report.log_path}", GRAY))
        time.sleep(2)


def _profile_key(host: str, game_port: int) -> str:
    return f"{host}:{game_port}"


def _print_server_lock(report: DetectionReport) -> None:
    assert report.selected is not None
    selected = report.selected
    print()
    _rule("=", color=GREEN)
    print(_paint("SERVER LOCK ACQUIRED", GREEN, bold=True))
    print(f"  Game endpoint : {_paint(selected.endpoint, WHITE, bold=True)}")
    print(f"  Evidence      : {selected.source} ({selected.confidence:.0%} confidence)")
    print(f"  Observed      : {selected.observed_at or 'current process socket'}")
    if report.log_path:
        print(f"  Rust log      : {report.log_path}")
    if report.battlemetrics:
        bm = report.battlemetrics
        print(f"  BattleMetrics : ID {bm.get('id') or '?'} - {bm.get('name') or 'Unnamed server'}")
    if report.rust_app_port:
        print(
            f"  Rust+ port    : {_paint(str(report.rust_app_port), GREEN, bold=True)} "
            f"({report.rust_app_port_source or 'automatic'})"
        )
    else:
        print(_paint("  Rust+ port    : not published by automatic sources", YELLOW))
    for warning in report.warnings:
        print(_paint(f"  Warning       : {warning}", YELLOW))
    _rule("=", color=GREEN)


def _load_current_profile(
    store: JsonStore,
    report: DetectionReport,
) -> tuple[str, RustCredentials]:
    assert report.selected is not None
    selected = report.selected
    key = _profile_key(selected.host, selected.port)
    profiles = dict(store.get("credential_profiles", {}) or {})
    identity = dict(store.get("player_identity", {}) or {})
    legacy = RustCredentials.from_dict(store.get("credentials", {}))
    saved = RustCredentials.from_dict(profiles.get(key, {}))

    steam_id = (
        saved.steam_id
        or int(identity.get("steam_id", 0) or 0)
        or legacy.steam_id
    )
    current = RustCredentials(
        host=saved.host or selected.host,
        port=saved.port,
        steam_id=steam_id,
        player_token=saved.player_token,
    )

    if report.rust_app_port:
        saved_pairing = bool(
            saved.player_token and saved.host and saved.port
        )
        saved_split_endpoint = bool(
            saved_pairing
            and saved.host.casefold() != selected.host.casefold()
        )
        heuristic_source = (
            str(report.rust_app_port_source or "").casefold()
            == "facepunch_default_plus_67_websocket_probe"
        )

        if saved_split_endpoint:
            print(
                _paint(
                    "[PROFILE] Retaining the saved Rust+ companion "
                    f"endpoint {saved.host}:{saved.port}; automatic "
                    "discovery describes the game endpoint.",
                    GRAY,
                )
            )
        elif (
            saved_pairing
            and heuristic_source
            and saved.port != report.rust_app_port
        ):
            print(
                _paint(
                    "[PROFILE] Retaining saved Rust+ port "
                    f"{saved.port}; discovered port "
                    f"{report.rust_app_port} is a verified default "
                    "candidate, not a server-published app.port.",
                    GRAY,
                )
            )
        else:
            if current.port and current.port != report.rust_app_port:
                print(
                    _paint(
                        f"[PORT UPDATE] Saved port {current.port} "
                        f"changed to published port {report.rust_app_port}.",
                        YELLOW,
                    )
                )
            current.port = report.rust_app_port

    return key, current





def _missing_fields(current: RustCredentials) -> list[str]:
    result: list[str] = []
    if not current.steam_id:
        result.append("Steam ID")
    if not current.port:
        result.append("Rust+ companion port")
    if not current.player_token:
        result.append("Rust+ player token")
    return result


def _save_profile(
    store: JsonStore,
    key: str,
    current: RustCredentials,
    report: DetectionReport,
    *,
    pairing_source: str = "",
) -> None:
    profiles = dict(store.get("credential_profiles", {}) or {})
    profiles[key] = current.to_dict()
    store.set("credential_profiles", profiles)
    store.set("credentials", current.to_dict())
    store.set("player_identity", {"steam_id": current.steam_id})

    metadata = dict(
        store.get("credential_profile_metadata", {}) or {}
    )
    metadata[key] = {
        "updated_at": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "game_endpoint": key,
        "rustplus_endpoint": (
            f"{current.host}:{current.port}"
            if current.host and current.port
            else ""
        ),
        "rust_app_port_source": (
            report.rust_app_port_source
            or pairing_source
            or "saved/manual"
        ),
        "pairing_source": pairing_source,
        "battlemetrics_id": str(
            report.battlemetrics.get("id") or ""
        ),
    }
    store.set("credential_profile_metadata", metadata)



def _apply_pairing_record(
    current: RustCredentials,
    record: PairingRecord,
    expected_host: str,
) -> bool:
    companion_host = str(
        record.host or expected_host or ""
    ).strip().strip("[]")
    if not companion_host:
        print(
            _paint(
                "[REJECTED] Pairing data contained no server host.",
                RED,
            )
        )
        return False

    if record.host and not record.matches_host(expected_host):
        print(
            _paint(
                "[ENDPOINT SPLIT] The game endpoint is "
                f"{expected_host}; Rust+ supplied companion endpoint "
                f"{record.host}:{record.port}.",
                YELLOW,
            )
        )
        print(
            _paint(
                "This is valid on proxied or multi-endpoint servers. "
                "The launcher will verify the Rust+ socket before opening "
                "the GUI.",
                WHITE,
            )
        )

    current.host = companion_host
    current.port = record.port or current.port
    current.steam_id = record.steam_id or current.steam_id
    current.player_token = record.player_token or current.player_token
    return True




def _import_pairing_text(current: RustCredentials, expected_host: str) -> str:
    print(_paint("Paste one-line Rust+ pairing JSON or a pairing JSON file path.", WHITE))
    raw = input(_paint("> Pairing JSON / file: ", AMBER)).strip()
    record = parse_pairing_payload(raw, source="launcher_pairing_import")
    if record is None:
        print(_paint("[INVALID] No pairing fields were found.", RED))
        return ""
    if not _apply_pairing_record(current, record, expected_host):
        return ""
    print(_paint("[IMPORTED] Pairing data matches the detected server.", GREEN))
    return record.source


def _find_fcm_config() -> dict[str, Any] | None:
    if FCM_CONFIG_PATH.is_file():
        config = load_fcm_config(FCM_CONFIG_PATH)
        if config:
            return config
    for path in (
        Path.cwd() / "rustplus.py.config.json",
        Path.home() / "Downloads" / "rustplus.py.config.json",
    ):
        if path.is_file():
            config = load_fcm_config(path)
            if config:
                save_fcm_config(FCM_CONFIG_PATH, config)
                return config
    return None


def _request_fcm_config() -> dict[str, Any] | None:
    return request_or_register_fcm_config()


def _cleanup_lingering_receiver_at_startup() -> None:
    config = _find_fcm_config()
    if not config or config.get("facepunch_registered") is False:
        return
    try:
        cleaned = cleanup_lingering_fcm_registration(
            config,
            status=lambda message: print(
                f"[PAIRING RECEIVER] {message}"
            ),
        )
    except FCMRegistrationError as exc:
        print(
            _paint(
                "[PAIRING RECEIVER WARNING] A legacy persistent "
                f"desktop registration could not be removed yet: {exc}",
                YELLOW,
            )
        )
        print(
            _paint(
                "The launcher will retry cleanup next time. "
                "Saved server profiles are unaffected.",
                GRAY,
            )
        )
        return
    if cleaned:
        print(
            _paint(
                "[PAIRING RECEIVER] Legacy persistent registration "
                "was removed. Future receivers are pairing-only.",
                GREEN,
            )
        )
def _listen_for_pairing(
    current: RustCredentials,
    expected_host: str,
    finder: RustServerFinder,
) -> str:
    config = _find_fcm_config() or _request_fcm_config()
    if config is None:
        return ""

    print()
    print(_paint("PAIRING RECEIVER CONNECTING", CYAN, bold=True))
    inbox = PairingNotificationInbox(config)
    inbox.start()
    ready = inbox.wait_until_ready(timeout=12.0)
    if ready:
        print(
            _paint(
                "PAIRING RECEIVER CONNECTED TO GOOGLE PUSH",
                GREEN,
                bold=True,
            )
        )
    else:
        print(
            _paint(
                "[PAIRING RECEIVER] Login readiness was not confirmed, "
                "but the listener is alive. Extending stale cleanup.",
                YELLOW,
            )
        )

    print(
        _paint(
            "[FRESHNESS GATE] Clearing queued Rust+ pushes before "
            "activating the temporary receiver...",
            YELLOW,
        )
    )
    discarded = inbox.drain_replayed(
        quiet_period=2.0 if ready else 3.0,
        max_wait=12.0 if ready else 16.0,
        process_alive=lambda: finder.get_rust_process_session().running,
    )

    registered = False
    try:
        refreshed = refresh_fcm_registration(
            config,
            status=lambda message: print(
                f"[PAIRING SETUP] {message}"
            ),
        )
        if refreshed is None:
            print(
                _paint(
                    "[PAIRING SETUP FAILED] The temporary receiver "
                    "could not be activated.",
                    RED,
                    bold=True,
                )
            )
            return ""
        config = refreshed
        registered = True

        print()
        print(
            _paint(
                "PAIRING RECEIVER ARMED FOR A FRESH REQUEST",
                GREEN,
                bold=True,
            )
        )
        print(
            _paint(
                "This desktop receiver is temporary and will be "
                "removed automatically after this attempt.",
                GREEN,
            )
        )
        print(_paint("No Enter key is required.", GREEN, bold=True))
        print(
            _paint(
                "NOW perform exactly one action in Rust:",
                WHITE,
                bold=True,
            )
        )
        print("  - If Rust shows Pair With Server, choose it once.")
        print(
            "  - If Rust still shows notifications enabled, reopen the "
            "Rust+ menu after cleanup and use Resend once if needed."
        )
        print(
            _paint(
                "Only this desktop Expo token is temporary. The official "
                "phone registration is not removed.",
                YELLOW,
            )
        )
        if discarded:
            print(
                _paint(
                    f"[FRESHNESS GATE] Discarded {discarded} queued "
                    "pairing payload(s).",
                    YELLOW,
                )
            )
        print(
            _paint(
                "Waiting for the fresh request and final player token. "
                "Ctrl+C cancels.",
                GRAY,
            )
        )

        record = inbox.wait_for(
            expected_host,
            process_alive=lambda: finder.get_rust_process_session().running,
        )
        if record is None:
            print(
                _paint(
                    "[PAIRING STOPPED] Rust closed before a fresh "
                    "notification arrived.",
                    YELLOW,
                )
            )
            return ""
        if not _apply_pairing_record(current, record, expected_host):
            return ""
        print(
            _paint(
                "[PAIRING RECEIVED] Fresh port, Steam ID, and player "
                "token imported automatically.",
                GREEN,
                bold=True,
            )
        )
        return record.source
    except FCMRegistrationError as exc:
        print(_paint(f"[PAIRING SETUP FAILED] {exc}", RED, bold=True))
        return ""
    finally:
        if registered or config.get("facepunch_registered") is not False:
            try:
                unregister_fcm_registration(
                    config,
                    status=lambda message: print(
                        f"[PAIRING CLEANUP] {message}"
                    ),
                )
            except FCMRegistrationError as exc:
                print(
                    _paint(
                        "[PAIRING CLEANUP WARNING] The temporary desktop "
                        f"receiver could not be removed: {exc}",
                        YELLOW,
                    )
                )
                print(
                    _paint(
                        "Cleanup will be retried on the next launcher start.",
                        GRAY,
                    )
                )







def _prompt_required_int(label: str, validator: Callable[[int], bool]) -> int:
    while True:
        raw = input(_paint(f"> {label} (visible input): ", AMBER)).strip()
        try:
            value = int(raw)
        except ValueError:
            print(_paint("  Enter a signed integer; a leading minus is allowed.", RED))
            continue
        if validator(value):
            return value
        print(_paint("  Value is outside the accepted range.", RED))


def _manual_complete_profile(
    current: RustCredentials,
) -> None:
    if not current.steam_id:
        current.steam_id = _prompt_required_int(
            "Steam ID (17 digits)",
            lambda value: len(str(value)) == 17,
        )
    if not current.port:
        current.port = _prompt_required_int(
            "Rust+ companion/app port",
            lambda value: 1 <= value <= 65535,
        )
    if not current.player_token:
        while True:
            value = _prompt_required_int(
                "Rust+ player token (signed int32; non-zero)",
                lambda candidate: candidate != 0,
            )
            try:
                current.player_token = normalize_player_token(value)
            except ValueError as exc:
                print(_paint(f"  {exc}", RED))
                continue
            break



def _retry_port_discovery(store: JsonStore) -> DetectionReport | None:
    finder = RustServerFinder(store)
    session = finder.get_rust_process_session()
    if not session.running:
        print(_paint("[FAILED] Rust is no longer running.", RED))
        return None
    report = finder.detect_once(
        enrich=True,
        require_running_process=True,
        session_started_at=session.started_at_epoch,
        current_session_only=True,
    )
    if report.selected is None:
        print(_paint("[FAILED] The current server connection could not be reconfirmed.", RED))
        return None
    if report.rust_app_port:
        print(_paint(f"[FOUND] Rust+ port {report.rust_app_port} via {report.rust_app_port_source}.", GREEN))
    else:
        print(_paint("[NOT PUBLISHED] Automatic sources still expose no Rust+ port.", YELLOW))
    return report


def _collect_missing_fields(
    store: JsonStore,
    report: DetectionReport,
    key: str,
    current: RustCredentials,
) -> tuple[DetectionReport, str]:
    assert report.selected is not None
    finder = RustServerFinder(store)
    pairing_source = ""

    while not current.is_complete():
        print()
        print(_paint(f"SERVER PROFILE INCOMPLETE: {', '.join(_missing_fields(current))}", YELLOW, bold=True))
        print(_paint("The GUI stays locked until this exact server profile is complete.", GRAY))
        print("  [A] Auto-receive a fresh Rust+ pairing notification")
        print("  [P] Paste/import a Rust+ pairing payload")
        print("  [R] Retry log, BattleMetrics, and A2S app-port discovery")
        print("  [M] Enter only the missing values manually")
        choice = input(_paint("> Select A / P / R / M: ", AMBER)).strip().casefold()

        if choice == "a":
            pairing_source = _listen_for_pairing(current, report.selected.host, finder) or pairing_source
        elif choice == "p":
            pairing_source = _import_pairing_text(current, report.selected.host) or pairing_source
        elif choice == "r":
            refreshed = _retry_port_discovery(store)
            if refreshed:
                report = refreshed
                current.port = refreshed.rust_app_port or current.port
        elif choice == "m":
            _manual_complete_profile(current)
        else:
            print(_paint("Choose A, P, R, or M.", RED))
            continue
        _save_profile(store, key, current, report, pairing_source=pairing_source)

    return report, pairing_source


def _edit_profile(current: RustCredentials) -> None:
    print(
        _paint(
            "Enter a replacement value, or press Enter to keep the "
            "current value.",
            GRAY,
        )
    )
    steam = input(
        f"> Steam ID [{current.steam_id}]: "
    ).strip()
    port = input(
        f"> Rust+ port [{current.port}]: "
    ).strip()
    token = input(
        f"> Player token [{current.player_token}] "
        "(signed int32, visible): "
    ).strip()

    if steam:
        value = int(steam)
        if len(str(value)) != 17:
            raise ValueError(
                "Steam ID must contain 17 digits"
            )
        current.steam_id = value

    if port:
        value = int(port)
        if not 1 <= value <= 65535:
            raise ValueError(
                "Rust+ port must be between 1 and 65535"
            )
        current.port = value

    if token:
        value = normalize_player_token(token)
        if value == 0:
            raise ValueError(
                "player token must be a non-zero signed int32"
            )
        current.player_token = value



def _validate_profile(
    store: JsonStore,
    report: DetectionReport,
    key: str,
    current: RustCredentials,
    pairing_source: str,
) -> ServerSnapshot:
    client = RustPlusClient()
    while True:
        _status_line(
            "VALIDATING RUST+ WEBSOCKET  "
            f"{current.host}:{current.port}  "
            f"STEAM={current.steam_id}",
            CYAN,
        )
        try:
            snapshot = client.fetch_snapshot(current)
        except Exception as exc:
            reason = str(exc).strip()
            print(
                _paint(
                    f"[RUST+ VALIDATION FAILED] {reason}",
                    RED,
                    bold=True,
                )
            )
            compact_reason = "".join(
                character
                for character in reason.casefold()
                if character.isalnum()
            )
            if "notfound" in compact_reason:
                print(
                    _paint(
                        "[STALE PROFILE] These credentials are not "
                        "authorized for the detected game server.",
                        YELLOW,
                        bold=True,
                    )
                )
                print(
                    _paint(
                        "The invalid Rust+ endpoint and player token "
                        "have been removed. Steam ID is retained.",
                        WHITE,
                    )
                )
                assert report.selected is not None
                current.host = report.selected.host
                current.port = report.rust_app_port or 0
                current.player_token = 0
                _save_profile(
                    store,
                    key,
                    current,
                    report,
                    pairing_source=(
                        "validation_reset:not_found"
                    ),
                )
                report, source = _collect_missing_fields(
                    store,
                    report,
                    key,
                    current,
                )
                pairing_source = source or pairing_source
                continue

            print("  [R] Retry the same values")
            print("  [E] Edit this server profile")
            print("  [P] Receive/import a new pairing payload")
            print("  [F] Forget the saved Rust+ pairing and start fresh")
            choice = input(
                _paint(
                    "> Select R / E / P / F: ",
                    AMBER,
                )
            ).strip().casefold()

            if choice == "r":
                continue
            if choice == "e":
                try:
                    _edit_profile(current)
                except (TypeError, ValueError) as edit_error:
                    print(
                        _paint(
                            f"[INVALID] {edit_error}",
                            RED,
                        )
                    )
                    continue
                _save_profile(
                    store,
                    key,
                    current,
                    report,
                    pairing_source=pairing_source,
                )
                continue
            if choice == "p":
                assert report.selected is not None
                finder = RustServerFinder(store)
                source = _listen_for_pairing(
                    current,
                    report.selected.host,
                    finder,
                )
                if not source:
                    source = _import_pairing_text(
                        current,
                        report.selected.host,
                    )
                pairing_source = source or pairing_source
                _save_profile(
                    store,
                    key,
                    current,
                    report,
                    pairing_source=pairing_source,
                )
                continue
            if choice == "f":
                assert report.selected is not None
                current.host = report.selected.host
                current.port = report.rust_app_port or 0
                current.player_token = 0
                _save_profile(
                    store,
                    key,
                    current,
                    report,
                    pairing_source=(
                        "validation_reset:user"
                    ),
                )
                report, source = _collect_missing_fields(
                    store,
                    report,
                    key,
                    current,
                )
                pairing_source = source or pairing_source
                continue

            print(_paint("Choose R, E, P, or F.", RED))
            continue

        print(
            _paint(
                "[RUST+ VERIFIED] Live server and team authorization "
                "succeeded.",
                GREEN,
                bold=True,
            )
        )
        _save_profile(
            store,
            key,
            current,
            report,
            pairing_source=pairing_source,
        )
        store.set(
            "bootstrap_snapshot",
            snapshot.to_dict(),
        )
        return snapshot




def prepare_credentials(store: JsonStore, report: DetectionReport) -> RustCredentials:
    assert report.selected is not None
    _print_server_lock(report)
    key, current = _load_current_profile(store, report)
    loaded = []
    if current.steam_id:
        loaded.append("Steam ID")
    if current.port:
        loaded.append("Rust+ port")
    if current.player_token:
        loaded.append("player token")
    if loaded:
        print(_paint(f"[PROFILE] Loaded for {key}: {', '.join(loaded)}.", GREEN))

    report, source = _collect_missing_fields(store, report, key, current)
    _validate_profile(store, report, key, current, source)
    return current



def launch_gui(
    saved_profile_key: str = "",
) -> int:
    from rust_companion_plus.app import RustCompanionApp

    if saved_profile_key:
        print(
            _paint(
                "\nOPENING SAVED SERVER PROFILE — Rust process "
                "detection is skipped. Cached data loads immediately; "
                "saved Rust+ credentials continue refreshing when the "
                "server and internet are reachable.\n",
                GREEN,
                bold=True,
            )
        )
    else:
        print(
            _paint(
                "\nALL GATES GREEN — launching Rust Companion+ "
                "with the verified live profile.\n",
                GREEN,
                bold=True,
            )
        )

    app = (
        RustCompanionApp(
            saved_profile_key=saved_profile_key,
        )
        if saved_profile_key
        else RustCompanionApp()
    )
    app.mainloop()
    return 0




def _parse_args(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", action="store_true")
    parser.add_argument(
        "--open-data-folder",
        action="store_true",
    )
    parser.add_argument(
        "--reset-integration-setup",
        action="store_true",
    )
    parser.add_argument(
        "--saved-profile",
        default="",
        help=(
            "Open one saved game-server profile without "
            "waiting for Rust."
        ),
    )
    return parser.parse_args(argv)




def main(
    argv: list[str] | None = None,
) -> int:
    # RUST_COMPANION_DIAGNOSTICS_BEGIN
    if os.environ.get(
        "RUST_COMPANION_DEBUG",
        "",
    ).strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        from rust_companion_plus.debug_tools import (
            install_debug_runtime,
        )

        install_debug_runtime(sys.modules[__name__])
    # RUST_COMPANION_DIAGNOSTICS_END

    args = _parse_args(argv)
    if args.data_dir:
        print(APP_DATA_DIR)
        return 0
    if args.open_data_folder:
        if os.name == "nt":
            os.startfile(APP_DATA_DIR)  # type: ignore[attr-defined]
        else:
            print(APP_DATA_DIR)
        return 0

    print_header()
    store = JsonStore()
    if args.reset_integration_setup:
        store.set("launcher_setup_version", 0)
    configure_first_run(store)
    _cleanup_lingering_receiver_at_startup()

    try:
        if args.saved_profile:
            vault = ServerProfileVault(store)
            if vault.get(args.saved_profile) is None:
                print(
                    _paint(
                        "[SAVED PROFILE NOT FOUND] "
                        f"{args.saved_profile}",
                        RED,
                        bold=True,
                    )
                )
                return 2
            return launch_gui(args.saved_profile)

        mode, saved_key = choose_launch_mode(store)
        if mode == "quit":
            return 0
        if mode == "saved":
            return launch_gui(saved_key)

        report = wait_for_server(store)
        prepare_credentials(store, report)
        return launch_gui()
    except KeyboardInterrupt:
        print(
            _paint(
                "\nLauncher stopped. The GUI was not opened.",
                YELLOW,
            )
        )
        return 130



if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
