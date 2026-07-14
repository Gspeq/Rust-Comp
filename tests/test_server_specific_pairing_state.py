from __future__ import annotations

import unittest

from rust_companion_plus import bootstrap


class _Store:
    def __init__(self, profiles=None, credentials=None):
        self.values = {
            "credential_profiles": profiles or {},
            "credentials": credentials or {},
            "player_identity": {},
        }

    def get(self, key, default=None):
        return self.values.get(key, default)


class _Selected:
    host = "203.0.113.50"
    port = 28015


class _Report:
    selected = _Selected()
    rust_app_port = 28082
    rust_app_port_source = "rust_log"
    battlemetrics = {}


class ServerSpecificPairingStateTests(unittest.TestCase):
    def test_new_server_is_unpaired_even_with_global_legacy_credentials(self):
        store = _Store(
            credentials={
                "host": "198.51.100.10",
                "port": 28082,
                "steam_id": 76561199121283118,
                "player_token": -123,
            }
        )
        key, current = bootstrap._load_current_profile(store, _Report())
        self.assertEqual("203.0.113.50:28015", key)
        self.assertEqual("unpaired", bootstrap._server_pairing_state(store, key))
        self.assertEqual(0, current.player_token)

    def test_exact_server_profile_is_saved(self):
        key = "203.0.113.50:28015"
        store = _Store(
            profiles={
                key: {
                    "host": "203.0.113.50",
                    "port": 28082,
                    "steam_id": 76561199121283118,
                    "player_token": -456,
                }
            }
        )
        self.assertEqual("saved", bootstrap._server_pairing_state(store, key))

    def test_other_server_profile_does_not_count(self):
        store = _Store(
            profiles={
                "198.51.100.10:28015": {
                    "host": "198.51.100.10",
                    "port": 28082,
                    "steam_id": 76561199121283118,
                    "player_token": -456,
                }
            }
        )
        self.assertEqual(
            "unpaired",
            bootstrap._server_pairing_state(
                store,
                "203.0.113.50:28015",
            ),
        )

    def test_partial_exact_profile_is_incomplete(self):
        key = "203.0.113.50:28015"
        store = _Store(
            profiles={
                key: {
                    "host": "203.0.113.50",
                    "port": 28082,
                    "steam_id": 76561199121283118,
                    "player_token": 0,
                }
            }
        )
        self.assertEqual("incomplete", bootstrap._server_pairing_state(store, key))


if __name__ == "__main__":
    unittest.main()
