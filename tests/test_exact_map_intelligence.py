from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from rust_companion_plus.services.exact_map_intelligence import (
    _write_monument_proximity_layer,
    normalize_monuments,
)


class ExactMapIntelligenceTests(unittest.TestCase):
    def monument_payload(self) -> dict:
        return {
            "map": {
                "world_size": 3700,
            },
            "monuments": [
                {
                    "name": "launch_site_1",
                    "prefab_path": (
                        "assets/bundled/prefabs/autospawn/"
                        "monument/large/launch_site_1.prefab"
                    ),
                    "position": {
                        "x": 100.0,
                        "y": 12.0,
                        "z": -200.0,
                    },
                    "heading_degrees": 90.0,
                    "metadata": {
                        "display_name": "Launch Site",
                        "classification": {
                            "kind": "monument",
                            "environment": "surface",
                            "size_class": "large",
                        },
                        "gameplay": {
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
                        },
                    },
                }
            ],
        }

    def test_normalization_keeps_name_position_and_gameplay(self) -> None:
        rows = normalize_monuments(
            self.monument_payload()
        )
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual("Launch Site", row["name"])
        self.assertEqual(100.0, row["x"])
        self.assertEqual(-200.0, row["y"])
        self.assertEqual("large", row["size_class"])
        self.assertEqual(1, row["recycler_count"])
        self.assertEqual(
            ["green", "blue", "red"],
            row["keycard_requirements"],
        )
        self.assertEqual(3, row["loot_tier"])
        self.assertGreaterEqual(row["radius_m"], 350)

    def test_exact_monument_layer_is_generated(self) -> None:
        rows = normalize_monuments(
            self.monument_payload()
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = _write_monument_proximity_layer(
                rows,
                output_dir=Path(temporary),
                world_size=3700,
                resolution=256,
            )
            self.assertTrue(path.is_file())
            with Image.open(path) as image:
                self.assertEqual((256, 256), image.size)
                self.assertGreater(
                    image.getbbox()[2],
                    image.getbbox()[0],
                )

    def test_parser_dependency_is_declared(self) -> None:
        root = Path(__file__).resolve().parents[1]
        requirements = (
            root / "requirements.txt"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "rust-map-parser==0.2.4",
            requirements,
        )


if __name__ == "__main__":
    unittest.main()
