
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rust_companion_plus.app import AppContext
from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.rustplus_client import (
    ServerSnapshot,
)
from rust_companion_plus.storage import JsonStore


class AutomaticThreatAndDeathTests(unittest.TestCase):
    def context(self, path: Path) -> AppContext:
        return AppContext(
            store=JsonStore(path),
            rust=object(),  # type: ignore[arg-type]
            credentials=RustCredentials(
                host="203.0.113.10",
                port=28082,
                steam_id=76561199121283118,
                player_token=-123,
            ),
        )

    def test_self_death_updates_threats_and_last_ten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context(
                Path(temporary) / "store.json"
            )
            previous = ServerSnapshot(
                server={"size": 3700},
                team=[
                    {
                        "steam_id": 76561199121283118,
                        "name": "Taylor",
                        "x": 350.0,
                        "y": -525.0,
                        "is_online": True,
                        "is_alive": True,
                    }
                ],
                markers=[],
            )
            current = ServerSnapshot(
                server={"size": 3700},
                team=[
                    {
                        "steam_id": 76561199121283118,
                        "name": "Taylor",
                        "x": 350.0,
                        "y": -525.0,
                        "is_online": True,
                        "is_alive": False,
                        "death_time": 100,
                    }
                ],
                markers=[],
            )

            context._record_snapshot_changes(
                previous,
                current,
            )

            threats = context.store.get("threats", [])
            deaths = context.store.get("death_history", [])
            self.assertEqual(1, len(threats))
            self.assertEqual("death", threats[0]["event_type"])
            self.assertEqual("Unknown", threats[0]["attacker"])
            self.assertEqual(1, len(deaths))
            self.assertEqual("Taylor", deaths[0]["name"])
            self.assertTrue(deaths[0]["grid"])
            self.assertAlmostEqual(350.0, deaths[0]["x"])
            self.assertAlmostEqual(-525.0, deaths[0]["y"])

    def test_world_event_updates_threat_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context(
                Path(temporary) / "store.json"
            )
            previous = ServerSnapshot(
                server={"size": 3700},
                team=[],
                markers=[],
            )
            current = ServerSnapshot(
                server={"size": 3700},
                team=[],
                markers=[
                    {
                        "id": 42,
                        "type": 8,
                        "x": 100,
                        "y": 200,
                    }
                ],
            )

            context._record_snapshot_changes(
                previous,
                current,
            )

            threats = context.store.get("threats", [])
            self.assertEqual(1, len(threats))
            self.assertEqual(
                "world_event",
                threats[0]["event_type"],
            )
            self.assertEqual(
                "Patrol Helicopter",
                threats[0]["attacker"],
            )

    def test_tools_page_keeps_only_useful_utilities(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root
            / "rust_companion_plus"
            / "ui"
            / "tabs"
            / "tools.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"TC Upkeep"', source)
        self.assertIn('"Recycle"', source)
        self.assertIn('"Smart Devices"', source)
        self.assertNotIn('"Building"', source)
        self.assertNotIn('"Farming"', source)
        self.assertNotIn('"Plants"', source)
        self.assertNotIn('"Loot"', source)


if __name__ == "__main__":
    unittest.main()
