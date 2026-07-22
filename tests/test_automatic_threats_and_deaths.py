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


class AutomaticDeathAndWorkflowTests(unittest.TestCase):
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

    def test_self_death_updates_last_ten_positions(self) -> None:
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

            deaths = context.store.get(
                "death_history",
                [],
            )
            self.assertEqual(1, len(deaths))
            self.assertEqual(
                "Taylor",
                deaths[0]["name"],
            )
            self.assertTrue(deaths[0]["grid"])
            self.assertAlmostEqual(
                350.0,
                deaths[0]["x"],
            )
            self.assertAlmostEqual(
                -525.0,
                deaths[0]["y"],
            )

    def test_threats_tab_is_removed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app = (
            root / "rust_companion_plus" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("ThreatsTab", app)
        self.assertNotIn('"Threats":', app)

    def test_map_starts_without_a_heatmap(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root
            / "rust_companion_plus"
            / "ui"
            / "tabs"
            / "map_tab.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'value=NO_HEATMAP',
            source,
        )
        self.assertIn(
            "Load & analyze current map",
            source,
        )
        self.assertIn(
            "View saved analyzed map",
            source,
        )
        self.assertIn(
            "force_refresh=True",
            source,
        )
        self.assertNotIn(
            'text="Analyze current map"',
            source,
        )

    def test_utilities_remove_tc_upkeep(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root
            / "rust_companion_plus"
            / "ui"
            / "tabs"
            / "tools.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"Grid & Distance"', source)
        self.assertIn('"Recycle"', source)
        self.assertNotIn('"Smart Devices"', source)
        self.assertNotIn('"TC Upkeep"', source)
        self.assertNotIn(
            "calculate_upkeep_hours",
            source,
        )

    def test_team_page_has_live_intelligence(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root
            / "rust_companion_plus"
            / "ui"
            / "tabs"
            / "team.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "Team Intelligence",
            source,
        )
        self.assertIn(
            "Monument",
            source,
        )
        self.assertIn(
            "My last 10 deaths",
            source,
        )
        self.assertIn(
            "TEAM POSITION SUMMARY",
            source,
        )


if __name__ == "__main__":
    unittest.main()
