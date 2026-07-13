from __future__ import annotations

import unittest
from unittest.mock import patch


from rust_companion_plus.bootstrap import (
    LAUNCHER_SETUP_VERSION,
    _load_current_profile,
    configure_first_run,
)
from rust_companion_plus.services.server_finder import DetectionReport, ServerCandidate


class MemoryStore:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class BootstrapTests(unittest.TestCase):
    def test_skipped_optional_keys_do_not_prompt_every_run(self) -> None:
        store = MemoryStore(
            {
                "launcher_setup_version": LAUNCHER_SETUP_VERSION,
                "api_keys": {"battlemetrics": "", "rustmaps": ""},
            }
        )
        with patch("builtins.input", side_effect=AssertionError("input should not be called")):
            configure_first_run(store)

    def test_server_token_is_not_reused_across_servers(self) -> None:
        store = MemoryStore(
            {
                "credentials": {
                    "host": "1.1.1.1",
                    "port": 28082,
                    "steam_id": 76561199121283118,
                    "player_token": 999,
                },
                "credential_profiles": {
                    "1.1.1.1:28015": {
                        "host": "1.1.1.1",
                        "port": 28082,
                        "steam_id": 76561199121283118,
                        "player_token": 999,
                    }
                },
                "player_identity": {"steam_id": 76561199121283118},
            }
        )
        report = DetectionReport(
            scanned_at="now",
            selected=ServerCandidate("2.2.2.2", 28015, "rust_log_raknet", 0.99),
        )
        key, credentials = _load_current_profile(store, report)
        self.assertEqual("2.2.2.2:28015", key)
        self.assertEqual(76561199121283118, credentials.steam_id)
        self.assertEqual(0, credentials.player_token)
        self.assertEqual(0, credentials.port)

    def test_automatic_port_updates_exact_server_profile(self) -> None:
        store = MemoryStore(
            {
                "credential_profiles": {
                    "2.2.2.2:28015": {
                        "host": "2.2.2.2",
                        "port": 11111,
                        "steam_id": 76561199121283118,
                        "player_token": 123,
                    }
                }
            }
        )
        report = DetectionReport(
            scanned_at="now",
            selected=ServerCandidate("2.2.2.2", 28015, "rust_log_raknet", 0.99),
            rust_app_port=28082,
            rust_app_port_source="a2s_rules:27017",
        )
        _, credentials = _load_current_profile(store, report)
        self.assertEqual(28082, credentials.port)
        self.assertEqual(123, credentials.player_token)


if __name__ == "__main__":
    unittest.main()
