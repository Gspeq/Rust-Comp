from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from rust_companion_plus.services.team_intelligence import (
    build_team_intelligence,
)


class TeamMonumentSummarySemanticsTests(unittest.TestCase):
    def _profile(self, root: Path) -> dict:
        parsed = root / "parsed_map"
        parsed.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "world_size": 3700,
            "monuments": [
                {
                    "name": "Launch Site",
                    "x": 100.0,
                    "y": 100.0,
                    "safe_zone": False,
                    "radius_m": 360.0,
                },
                {
                    "name": "Outpost",
                    "x": -800.0,
                    "y": 500.0,
                    "safe_zone": True,
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

    @staticmethod
    def _snapshot():
        return SimpleNamespace(
            server={"size": 3700},
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

    def test_teammate_count_excludes_local_player(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rows, summary = build_team_intelligence(
                self._snapshot(),
                steam_id=1,
                profile_record=self._profile(
                    Path(temporary)
                ),
            )

        self.assertEqual(
            3,
            sum(bool(row["at_monument"]) for row in rows),
        )
        self.assertEqual(
            2,
            summary["at_monument_count"],
        )
        self.assertEqual(
            2,
            summary["occupied_monument_count"],
        )
        self.assertEqual(
            "Launch Site",
            summary["self_monument_name"],
        )
        self.assertEqual(
            1,
            summary["safe_zone_count"],
        )

    def test_team_ui_labels_teammate_metric_clearly(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root
            / "rust_companion_plus"
            / "ui"
            / "tabs"
            / "team.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"TEAMMATES AT MONUMENTS"',
            source,
        )
        self.assertNotIn(
            '"AT NAMED MONUMENTS"',
            source,
        )


if __name__ == "__main__":
    unittest.main()
