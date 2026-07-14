from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from rust_companion_plus import bootstrap
from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.pairing import PairingRecord
from rust_companion_plus.services.rustplus_client import ServerSnapshot
from rust_companion_plus.services import fcm_registration


class _Selected:
    host = "208.103.169.97"
    port = 28010


class _Report:
    selected = _Selected()
    rust_app_port = 28077
    rust_app_port_source = "test"
    battlemetrics = {}


class _Store:
    def __init__(self, values=None) -> None:
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value) -> None:
        self.values[key] = value


class PairingLauncherBaselineTests(unittest.TestCase):
    def test_split_endpoint_is_accepted(self) -> None:
        current = RustCredentials(
            host="208.103.169.97",
            steam_id=76561199121283118,
        )
        record = PairingRecord(
            host="108.61.205.238",
            port=28084,
            steam_id=current.steam_id,
            player_token=-123456789,
        )

        accepted = bootstrap._apply_pairing_record(
            current,
            record,
            "208.103.169.97",
        )

        self.assertTrue(accepted)
        self.assertEqual("108.61.205.238", current.host)
        self.assertEqual(28084, current.port)
        self.assertEqual(-123456789, current.player_token)

    def test_saved_split_endpoint_is_restored(self) -> None:
        store = _Store(
            {
                "credential_profiles": {
                    "208.103.169.97:28010": {
                        "host": "108.61.205.238",
                        "port": 28084,
                        "steam_id": 76561199121283118,
                        "player_token": -123456789,
                    }
                }
            }
        )

        _key, current = bootstrap._load_current_profile(
            store,
            _Report(),
        )

        self.assertEqual("108.61.205.238", current.host)
        self.assertEqual(28084, current.port)

    def test_launcher_uses_ready_then_quiet_drain(self) -> None:
        rendered = inspect.getsource(
            bootstrap._listen_for_pairing
        )
        self.assertIn("wait_until_ready", rendered)
        self.assertIn("drain_replayed", rendered)
        self.assertIn(
            "PAIRING RECEIVER ARMED FOR A FRESH REQUEST",
            rendered,
        )
        self.assertNotIn("unpair and pair again", rendered.casefold())


    def test_saved_receiver_can_be_refreshed(self) -> None:
        config = {
            "rustplus_auth_token": "auth-token",
            "expo_push_token": "expo-token",
        }
        with (
            patch(
                "rust_companion_plus.services.fcm_registration._register_with_rust_plus"
            ) as registrar,
            patch(
                "rust_companion_plus.services.fcm_registration.save_fcm_config"
            ) as saver,
        ):
            refreshed = fcm_registration.refresh_fcm_registration(config)

        self.assertTrue(refreshed)
        registrar.assert_called_once_with("auth-token", "expo-token")
        saver.assert_called_once()
        self.assertIn("last_facepunch_refresh", config)

    def test_not_found_resets_stale_profile(self) -> None:
        store = _Store()
        current = RustCredentials(
            host="108.61.205.238",
            port=28084,
            steam_id=76561199121283118,
            player_token=-123456789,
        )
        fresh = RustCredentials(
            host="208.103.169.97",
            port=28077,
            steam_id=current.steam_id,
            player_token=987654321,
        )
        snapshot = ServerSnapshot({}, [], [])

        def recollect(_store, report, _key, credentials):
            self.assertEqual("208.103.169.97", credentials.host)
            self.assertEqual(28077, credentials.port)
            self.assertEqual(0, credentials.player_token)
            credentials.host = fresh.host
            credentials.port = fresh.port
            credentials.player_token = fresh.player_token
            return report, "fresh-test"

        with (
            patch(
                "rust_companion_plus.bootstrap.RustPlusClient.fetch_snapshot",
                side_effect=[RuntimeError("not_found"), snapshot],
            ),
            patch(
                "rust_companion_plus.bootstrap._collect_missing_fields",
                side_effect=recollect,
            ),
        ):
            result = bootstrap._validate_profile(
                store,
                _Report(),
                "208.103.169.97:28010",
                current,
                "stale-test",
            )

        self.assertIs(snapshot, result)
        self.assertEqual(fresh.player_token, current.player_token)


if __name__ == "__main__":
    unittest.main()
