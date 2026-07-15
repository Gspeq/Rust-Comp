from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.rustplus_client import (
    ServerSnapshot,
)
from rust_companion_plus.services.team_intelligence import (
    build_team_intelligence,
    compass_bearing,
    grid_for_world,
)


class TeamIntelligenceTests(unittest.TestCase):
    def profile_with_monuments(
        self,
        root: Path,
    ) -> dict:
        parsed = root / "parsed_map"
        parsed.mkdir(parents=True)
        (parsed / "map_resolved.json").write_text(
            json.dumps(
                {
                    "world_size": 3700,
                    "monuments": [
                        {
                            "label": "Monument marker 1",
                            "x_fraction": 0.5,
                            "y_fraction": 0.5,
                            "confidence": 0.9,
                        },
                        {
                            "label": "Monument marker 2",
                            "x_fraction": 0.8,
                            "y_fraction": 0.8,
                            "confidence": 0.8,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return {
            "assets": {
                "parsed_map_dir": str(parsed),
                "world_size": 3700,
            }
        }

    def test_live_rows_include_distance_grid_and_monument(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = self.profile_with_monuments(
                Path(temporary)
            )
            credentials = RustCredentials(
                steam_id=111,
            )
            snapshot = ServerSnapshot(
                server={"size": 3700},
                team=[
                    {
                        "steam_id": 111,
                        "name": "Taylor",
                        "x": 0,
                        "y": 0,
                        "is_online": True,
                        "is_alive": True,
                    },
                    {
                        "steam_id": 222,
                        "name": "Teammate",
                        "x": 100,
                        "y": 0,
                        "is_online": True,
                        "is_alive": True,
                    },
                ],
                markers=[],
            )

            rows, summary = build_team_intelligence(
                snapshot,
                steam_id=credentials.steam_id,
                profile_record=profile,
            )

            self.assertEqual(2, len(rows))
            self.assertTrue(rows[0]["is_self"])
            teammate = next(
                row
                for row in rows
                if row["name"] == "Teammate"
            )
            self.assertAlmostEqual(
                100.0,
                teammate["distance_m"],
            )
            self.assertTrue(teammate["grid"])
            self.assertTrue(
                teammate["near_monument"]
            )
            self.assertEqual(
                "Teammate",
                summary["nearest_teammate"],
            )
            self.assertAlmostEqual(
                100.0,
                summary["spread_m"],
            )
            self.assertEqual(
                2,
                summary["monument_markers"],
            )

    def test_grid_and_bearing_are_deterministic(self) -> None:
        grid = grid_for_world(
            0,
            0,
            3700,
        )
        self.assertNotEqual("?", grid)

        degrees, direction = compass_bearing(
            0,
            0,
            100,
            0,
        )
        self.assertAlmostEqual(90.0, degrees)
        self.assertEqual("E", direction)


if __name__ == "__main__":
    unittest.main()
