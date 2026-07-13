from __future__ import annotations

import unittest
from unittest.mock import patch

from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.battlemetrics_client import BattleMetricsServer
from rust_companion_plus.services.live_sync import IntegrationSettings, LiveSyncService
from rust_companion_plus.services.rustplus_client import ServerSnapshot
from rust_companion_plus.services.server_detection import ServerCandidate


class FakeDetector:
    def detect_all(self, preferred_host="", preferred_port=0):
        return [ServerCandidate("203.0.113.50", 28015, "test process", 99)]


class FakeBattleMetricsClient:
    def __init__(self, token=""):
        self.token = token

    def find_server(self, host, port=0):
        return BattleMetricsServer(
            server_id="bm-1",
            name="Example Rust",
            ip="203.0.113.50",
            port=28015,
            query_port=28017,
            players=100,
            max_players=200,
            status="online",
            rank=12,
            country="US",
            details={
                "rust_world_seed": 1234,
                "rust_world_size": 4500,
                "rust_app_port": 28082,
                "rust_last_wipe": "2026-07-09T18:00:00Z",
            },
        )


class FakeRustPlus:
    def fetch_snapshot(self, credentials):
        self.credentials = credentials
        return ServerSnapshot(
            {"name": "Rust+ Name", "seed": 1234, "size": 4500, "players": 101, "max_players": 200},
            [{"name": "Taylor", "is_online": True}],
            [],
            "12:00",
        )

    def fetch_map(self, credentials):
        return None


class LiveSyncTests(unittest.TestCase):
    @patch("rust_companion_plus.services.live_sync.BattleMetricsClient", FakeBattleMetricsClient)
    def test_profile_is_selected_and_metadata_is_merged(self):
        rust = FakeRustPlus()
        service = LiveSyncService(detector=FakeDetector(), rustplus=rust)
        profiles = {
            "203.0.113.50": {
                "host": "203.0.113.50",
                "port": 28082,
                "steam_id": 76561198000000000,
                "player_token": 123456,
            }
        }
        result = service.refresh(
            RustCredentials(),
            IntegrationSettings(rustmaps_api_key=""),
            credential_profiles=profiles,
        )
        self.assertTrue(result.rustplus_connected)
        self.assertEqual(result.credentials.port, 28082)
        self.assertEqual(result.snapshot.server["rank"], 12)
        self.assertEqual(result.snapshot.server["name"], "Rust+ Name")
        self.assertEqual(result.snapshot.server["last_wipe"], "2026-07-09T18:00:00Z")


if __name__ == "__main__":
    unittest.main()
