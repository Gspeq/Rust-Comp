from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from rust_companion_plus.services.team_intelligence import (
    build_team_intelligence,
)


class TeamIntelligenceTests(unittest.TestCase):
    def profile(
        self,
        root: Path,
    ) -> dict:
        parsed = root / "parsed_map"
        parsed.mkdir(
            parents=True,
            exist_ok=True,
        )
        payload = {
            "schema_version": 1,
            "world_size": 3700,
            "monuments": [
                {
                    "name": "Launch Site",
                    "x": 100.0,
                    "y": 100.0,
                    "size_class": "large",
                    "safe_zone": False,
                    "recycler_count": 1,
                    "keycard_requirements": [
                        "green",
                        "blue",
                        "red",
                    ],
                    "puzzle_type": (
                        "keycard_and_electrical"
                    ),
                    "loot_tier": 3,
                    "radius_m": 360.0,
                },
                {
                    "name": "Outpost",
                    "x": -800.0,
                    "y": 500.0,
                    "size_class": "medium",
                    "safe_zone": True,
                    "recycler_count": 3,
                    "keycard_requirements": [],
                    "puzzle_type": "none",
                    "loot_tier": 1,
                    "radius_m": 300.0,
                },
            ],
        }
        (parsed / "named_monuments.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        return {
            "assets": {
                "parsed_map_dir": str(parsed),
                "world_size": 3700,
            }
        }

    def snapshot(self):
        return SimpleNamespace(
            server={
                "size": 3700,
            },
            team=[
                {
                    "steam_id": 1,
                    "name": "Taylor",
                    "x": 120.0,
                    "y": 100.0,
                    "is_online": True,
                    "is_alive": True,
                },
                {
                    "steam_id": 2,
                    "name": "Alex",
                    "x": 180.0,
                    "y": 120.0,
                    "is_online": True,
                    "is_alive": True,
                },
                {
                    "steam_id": 3,
                    "name": "Morgan",
                    "x": -800.0,
                    "y": 520.0,
                    "is_online": True,
                    "is_alive": True,
                },
            ],
        )

    def test_named_monuments_and_gameplay_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rows, summary = build_team_intelligence(
                self.snapshot(),
                steam_id=1,
                profile_record=self.profile(
                    Path(temporary)
                ),
            )

        taylor = next(
            row
            for row in rows
            if row["name"] == "Taylor"
        )
        morgan = next(
            row
            for row in rows
            if row["name"] == "Morgan"
        )

        self.assertEqual(
            "Launch Site",
            taylor["monument_name"],
        )
        self.assertTrue(
            taylor["at_monument"]
        )
        self.assertIn(
            "Cards: Green + Blue + Red",
            taylor["monument_facts"],
        )
        self.assertIn(
            "Loot tier 3",
            taylor["monument_facts"],
        )

        self.assertEqual(
            "Outpost",
            morgan["monument_name"],
        )
        self.assertTrue(
            morgan["monument_safe_zone"],
        )
        self.assertIn(
            "Safe zone",
            morgan["monument_facts"],
        )
        self.assertEqual(
            2,
            summary["at_monument_count"],
        )
        self.assertEqual(
            1,
            summary["safe_zone_count"],
        )

    def test_isolation_and_nearest_teammate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rows, summary = build_team_intelligence(
                self.snapshot(),
                steam_id=1,
                profile_record=self.profile(
                    Path(temporary)
                ),
            )

        alex = next(
            row
            for row in rows
            if row["name"] == "Alex"
        )
        morgan = next(
            row
            for row in rows
            if row["name"] == "Morgan"
        )
        self.assertEqual(
            "Taylor",
            alex["nearest_teammate"],
        )
        self.assertLess(
            alex["nearest_teammate_distance_m"],
            100,
        )
        self.assertTrue(morgan["isolated"])
        self.assertIn(
            "Morgan",
            summary["isolated_members"],
        )
        self.assertEqual(
            ["Taylor", "Alex"],
            summary["monument_groups"][
                "Launch Site"
            ],
        )


if __name__ == "__main__":
    unittest.main()
