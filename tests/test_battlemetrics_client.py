from __future__ import annotations

import unittest

from rust_companion_plus.services.battlemetrics_client import BattleMetricsClient, BattleMetricsServer


RESOURCE = {
    "type": "server",
    "id": "12345",
    "attributes": {
        "name": "Example Rust",
        "ip": "203.0.113.50",
        "port": 28015,
        "portQuery": 28017,
        "players": 125,
        "maxPlayers": 200,
        "status": "online",
        "rank": 42,
        "country": "US",
        "details": {
            "rust_world_seed": "8675309",
            "rust_world_size": 4500,
            "rust_last_wipe": "2026-07-09T18:00:00Z",
            "rust_next_wipe": "2026-07-16T18:00:00Z",
            "rust_app_port": 28082,
            "rust_queued_players": 7,
        },
    },
}


class BattleMetricsModelTests(unittest.TestCase):
    def test_rust_details_are_normalized(self) -> None:
        server = BattleMetricsServer.from_resource(RESOURCE)
        self.assertEqual(server.seed, 8675309)
        self.assertEqual(server.world_size, 4500)
        self.assertEqual(server.companion_port, 28082)
        self.assertEqual(server.queue, 7)
        self.assertEqual(server.to_server_dict()["battlemetrics_id"], "12345")

    def test_exact_endpoint_is_ranked_first(self) -> None:
        other = {**RESOURCE, "id": "999", "attributes": {**RESOURCE["attributes"], "ip": "198.51.100.1"}}

        def fake_request(method, url, **kwargs):
            return {"data": [other, RESOURCE]}

        client = BattleMetricsClient(request=fake_request)
        server = client.find_server("203.0.113.50", 28015)
        self.assertEqual(server.server_id, "12345")


if __name__ == "__main__":
    unittest.main()
