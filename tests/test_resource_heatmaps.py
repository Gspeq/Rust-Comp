from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from rust_companion_plus.services.resource_heatmaps import (
    classify_resource,
    grid_reference,
    load_heatmap_bundle,
    rank_hotspots,
)


class ResourceClassificationTests(unittest.TestCase):
    def test_prefab_classification(self) -> None:
        self.assertEqual(
            classify_resource("assets/bundled/prefabs/autospawn/resource/ores/metal-ore.prefab"),
            "Metal",
        )
        self.assertEqual(classify_resource("roadside/junkpile_a.prefab"), "Junk Piles")
        self.assertEqual(classify_resource("animals/wolf/wolf.prefab"), "Wolf")


class HeatmapImportTests(unittest.TestCase):
    def test_parser_json_and_named_mask(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = [
                {
                    "i": "assets/bundled/prefabs/autospawn/resource/ores/stone-ore.prefab",
                    "c": "resource",
                    "x": -1000,
                    "y": 500,
                },
                {
                    "i": "assets/bundled/prefabs/autospawn/resource/ores/sulfur-ore.prefab",
                    "c": "resource",
                    "x": 1000,
                    "y": -500,
                },
            ]
            (root / "map_resolved.json").write_text(json.dumps(payload), encoding="utf-8")
            Image.new("L", (32, 32), 255).save(root / "metal_resource_heatmap.png")

            bundle = load_heatmap_bundle(root, world_size=4000)
            self.assertEqual(len(bundle.points["Stone"]), 1)
            self.assertEqual(len(bundle.points["Sulfur"]), 1)
            self.assertEqual(len(bundle.raster_layers["Metal"]), 1)
            self.assertAlmostEqual(bundle.points["Stone"][0].x_fraction, 0.25)
            self.assertAlmostEqual(bundle.points["Stone"][0].y_fraction, 0.625)

            hotspots = rank_hotspots(bundle, ["Stone", "Sulfur", "Metal"], limit=3)
            self.assertTrue(hotspots)

    def test_grid_reference(self) -> None:
        self.assertEqual(grid_reference(0.0, 1.0, 4500), "A0")
        self.assertIsInstance(grid_reference(0.5, 0.5, 4500), str)


if __name__ == "__main__":
    unittest.main()
