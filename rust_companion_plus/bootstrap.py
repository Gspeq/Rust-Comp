from __future__ import annotations

import getpass
import os
import sys
import time

from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.server_finder import DetectionReport, RustServerFinder
from rust_companion_plus.storage import JsonStore


ASCII_ART = r"""
  ____  _   _ ____ _____    ____ ___  __  __ ____   _    _   _ ___ ___  _   _ _
 |  _ \| | | / ___|_   _|  / ___/ _ \|  \/  |  _ \ / \  | \ | |_ _/ _ \| \ | | |
 | |_) | | | \___ \ | |   | |  | | | | |\/| | |_) / _ \ |  \| || | | | |  \| | |
 |  _ <| |_| |___) || |   | |__| |_| | |  | |  __/ ___ \| |\  || | |_| | |\  |_|
 |_| \_\\___/|____/ |_|    \____\___/|_|  |_|_| /_/   \_\_| \_|___\___/|_| \_(_)
"""


def print_header() -> None:
    os.system("cls" if os.name == "nt" else "clear")
    print(ASCII_ART)
    print("                         Developed by Taylor Marshall")
    print("=" * 92)


def configure_first_run(store: JsonStore) -> None:
    if store.get("launcher_setup_complete", False):
        return
    print("First-time integration setup")
    print("These keys are optional. Press Enter to use public/manual features only.\n")
    keys = dict(store.get("api_keys", {}) or {})
    if not keys.get("battlemetrics"):
        keys["battlemetrics"] = getpass.getpass("BattleMetrics API token (optional): ").strip()
    if not keys.get("rustmaps"):
        keys["rustmaps"] = getpass.getpass("RustMaps API key (optional): ").strip()
    store.set("api_keys", keys)
    store.set("launcher_setup_complete", True)


def wait_for_server(store: JsonStore) -> DetectionReport:
    finder = RustServerFinder(store)
    attempts = 0
    while True:
        attempts += 1
        report = finder.detect_once(enrich=False)
        if report.selected is not None:
            # Enrich only once after detection instead of hammering public APIs while waiting.
            return finder.detect_once(enrich=True)
        if attempts == 1 or attempts % 5 == 0:
            status = report.debug[-1] if report.debug else "No endpoint yet"
            print(f"[{time.strftime('%H:%M:%S')}] {status}")
            if report.log_path:
                print(f"             Watching: {report.log_path}")
        time.sleep(2)


def _profile_key(host: str, game_port: int) -> str:
    return f"{host}:{game_port}"


def prepare_credentials(store: JsonStore, report: DetectionReport) -> RustCredentials:
    assert report.selected is not None
    selected = report.selected
    detected = store.get("detected_server", {}) or {}
    key = _profile_key(selected.host, selected.port)
    profiles = dict(store.get("credential_profiles", {}) or {})
    existing = profiles.get(key)
    current = RustCredentials.from_dict(existing or store.get("credentials", {}))

    if existing is None and current.host and current.host != selected.host:
        # Never reuse a server-specific token against a different host.
        current = RustCredentials(host=selected.host, steam_id=current.steam_id)
    else:
        current.host = selected.host

    published_port = int(detected.get("rust_app_port", 0) or 0)
    if published_port and not current.port:
        current.port = published_port

    print("\nServer detected")
    print(f"  Game endpoint : {selected.endpoint}")
    print(f"  Evidence      : {selected.source} ({selected.confidence:.0%} confidence)")
    if report.log_path:
        print(f"  Rust log      : {report.log_path}")
    bm = report.battlemetrics
    if bm:
        print(f"  BattleMetrics : ID {bm.get('id') or '?'} - {bm.get('name') or 'Unnamed server'}")
    for warning in report.warnings:
        print(f"  Warning       : {warning}")

    print("\nRust+ pairing values are server-specific. Leave a field blank to launch in public-info mode.")
    if not current.steam_id:
        current.steam_id = _prompt_int("Steam ID (17 digits, optional): ")
    if not current.port:
        current.port = _prompt_int("Rust+ companion/app port (optional): ")
    if not current.player_token:
        current.player_token = _prompt_secret_int("Rust+ player token (optional): ")

    store.set("credentials", current.to_dict())
    profiles[key] = current.to_dict()
    store.set("credential_profiles", profiles)
    return current


def _prompt_int(prompt: str) -> int:
    raw = input(prompt).strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        print("  Invalid number; leaving it blank.")
        return 0


def _prompt_secret_int(prompt: str) -> int:
    raw = getpass.getpass(prompt).strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        print("  Invalid number; leaving it blank.")
        return 0


def launch_gui() -> int:
    from rust_companion_plus.app import RustCompanionApp

    print("\nLaunching Rust Companion+ with the detected server preloaded...\n")
    app = RustCompanionApp()
    app.mainloop()
    return 0


def main() -> int:
    print_header()
    store = JsonStore()
    configure_first_run(store)
    if store.get("launcher_setup_complete", False):
        print("Thanks! Waiting for you to join a Rust server...")
    try:
        report = wait_for_server(store)
        prepare_credentials(store, report)
        return launch_gui()
    except KeyboardInterrupt:
        print("\nLauncher stopped.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
