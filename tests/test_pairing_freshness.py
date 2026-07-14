from __future__ import annotations

import unittest
from unittest.mock import patch

from rust_companion_plus.bootstrap import _validate_profile
from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.rustplus_client import ServerSnapshot


class _Selected:
    host = "104.143.2.174"


class _Report:
    selected = _Selected()
    rust_app_port = 0
    rust_app_port_source = ""
    battlemetrics = {}


class _Store:
    def __init__(self) -> None:
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value) -> None:
        self.values[key] = value


class ValidationResetTests(unittest.TestCase):
    def test_not_found_clears_stale_pairing_before_recollection(self) -> None:
        store = _Store()
        current = RustCredentials(
            host="108.61.205.238",
            port=28084,
            steam_id=76561199121283118,
            player_token=123,
        )
        fresh = RustCredentials(
            host="192.0.2.10",
            port=28083,
            steam_id=current.steam_id,
            player_token=456,
        )
        snapshot = ServerSnapshot({}, [], [])

        def recollect(_store, report, _key, credentials):
            self.assertEqual("104.143.2.174", credentials.host)
            self.assertEqual(0, credentials.port)
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
            result = _validate_profile(
                store,
                _Report(),
                "104.143.2.174:28015",
                current,
                "stale-test",
            )

        self.assertIs(snapshot, result)
        self.assertEqual(fresh.host, current.host)
        self.assertEqual(fresh.port, current.port)
        self.assertEqual(fresh.player_token, current.player_token)


if __name__ == "__main__":
    unittest.main()
