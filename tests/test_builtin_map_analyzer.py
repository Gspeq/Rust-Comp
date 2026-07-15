from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from rust_companion_plus.services.builtin_map_analyzer import (
    analyze_map_image,
)
from rust_companion_plus.services.resource_heatmaps import (
    load_heatmap_bundle,
)


class BuiltinMapAnalyzerTests(unittest.TestCase):
    def test_analyzer_creates_layers_and_monument_markers(self) -> None:
        image = Image.new(
            "RGB",
            (512, 512),
            (65, 118, 58),
        )
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (0, 0, 120, 511),
            fill=(22, 84, 118),
        )
        draw.rectangle(
            (121, 0, 320, 230),
            fill=(190, 153, 85),
        )
        draw.rectangle(
            (321, 0, 511, 230),
            fill=(230, 232, 235),
        )
        draw.line(
            (140, 450, 450, 80),
            fill=(110, 105, 92),
            width=8,
        )
        draw.ellipse(
            (210, 260, 250, 300),
            fill=(245, 35, 35),
        )
        draw.ellipse(
            (360, 330, 404, 374),
            fill=(20, 155, 235),
        )

        with tempfile.TemporaryDirectory() as temporary:
            result = analyze_map_image(
                image,
                temporary,
                world_size=3700,
            )

            self.assertTrue(result.base_map_path.is_file())
            self.assertTrue(result.manifest_path.is_file())
            for layer in (
                "Stone",
                "Metal",
                "Sulfur",
                "Bear",
                "Wolf",
                "Horse",
                "Water",
                "Coastline",
                "Road Access",
                "Monument Proximity",
            ):
                self.assertIn(layer, result.layers)
                self.assertTrue(result.layers[layer].is_file())

            manifest = json.loads(
                result.manifest_path.read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                3700,
                manifest["world_size"],
            )
            self.assertEqual(
                (
                    "rust-companion-plus-"
                    "builtin-map-analysis-v2"
                ),
                manifest["format"],
            )
            self.assertGreaterEqual(
                len(manifest["monuments"]),
                2,
            )
            self.assertIn(
                "likelihood or habitat estimates",
                manifest["accuracy"]["predictive_layers"],
            )

            bundle = load_heatmap_bundle(
                Path(temporary),
                3700,
            )
            self.assertIn("Stone", bundle.resources)
            self.assertIn("Water", bundle.resources)
            self.assertIn(
                "Monument Proximity",
                bundle.resources,
            )

    def test_analyzer_source_has_no_external_executable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        server_profiles = (
            root
            / "rust_companion_plus"
            / "services"
            / "server_profiles.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "analyze_map_image",
            server_profiles,
        )
        self.assertNotIn(
            "MapParser.exe was not found",
            server_profiles,
        )
        self.assertNotIn(
            "find_map_parser()",
            server_profiles,
        )


if __name__ == "__main__":
    unittest.main()
