from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from rust_companion_plus.services.team_intelligence import (
    build_team_intelligence,
)


class TeamMonumentNumericNormalizationTests(unittest.TestCase):
    @staticmethod
    def _snapshot():
        return SimpleNamespace(
            server={"size": 3700},
            team=[
                {
                    "steam_id": 1,
                    "name": "Taylor",
                    "x": 100.0,
                    "y": 100.0,
                    "is_online": True,
                    "is_alive": True,
                },
                {
                    "steam_id": 2,
                    "name": "Alex",
                    "x": 140.0,
                    "y": 120.0,
                    "is_online": True,
                    "is_alive": True,
                },
            ],
        )

    @staticmethod
    def _profile(
        root: Path,
        *,
        recycler_count,
        loot_tier,
    ) -> dict:
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
                    "radius_m": 350.0,
                    "recycler_count": recycler_count,
                    "loot_tier": loot_tier,
                    "keycard_requirements": None,
                }
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

    def test_null_numeric_metadata_normalizes_to_zero(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rows, summary = build_team_intelligence(
                self._snapshot(),
                steam_id=1,
                profile_record=self._profile(
                    Path(temporary),
                    recycler_count=None,
                    loot_tier=None,
                ),
            )

        self.assertEqual(2, len(rows))
        self.assertEqual(
            0,
            rows[0]["monument_recycler_count"],
        )
        self.assertEqual(
            0,
            rows[0]["monument_loot_tier"],
        )
        self.assertEqual(
            [],
            rows[0]["monument_keycards"],
        )
        self.assertEqual(
            1,
            summary["at_monument_count"],
        )

    def test_malformed_numeric_metadata_does_not_crash(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rows, _summary = build_team_intelligence(
                self._snapshot(),
                steam_id=1,
                profile_record=self._profile(
                    Path(temporary),
                    recycler_count="unknown",
                    loot_tier="",
                ),
            )

        self.assertEqual(
            0,
            rows[1]["monument_recycler_count"],
        )
        self.assertEqual(
            0,
            rows[1]["monument_loot_tier"],
        )

    def test_numeric_strings_are_supported(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rows, _summary = build_team_intelligence(
                self._snapshot(),
                steam_id=1,
                profile_record=self._profile(
                    Path(temporary),
                    recycler_count="2",
                    loot_tier="3",
                ),
            )

        self.assertEqual(
            2,
            rows[0]["monument_recycler_count"],
        )
        self.assertEqual(
            3,
            rows[0]["monument_loot_tier"],
        )


if __name__ == "__main__":
    unittest.main()
