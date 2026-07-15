from __future__ import annotations

import unittest
from pathlib import Path

from rust_companion_plus.ui.tabs.electrical import (
    circuit_recommendations,
    setup_from_canvas,
)


class VisualElectricalCanvasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = {
            "Solar": {
                "category": "generation",
                "power_draw": 0,
                "max_output": 20,
                "capacity_rwm": 0,
                "output_limit": 0,
                "charge_efficiency": 1.0,
            },
            "Battery": {
                "category": "storage",
                "power_draw": 0,
                "max_output": 0,
                "capacity_rwm": 24000,
                "output_limit": 100,
                "charge_efficiency": 0.8,
            },
            "Turret": {
                "category": "load",
                "power_draw": 10,
                "max_output": 0,
                "capacity_rwm": 0,
                "output_limit": 0,
                "charge_efficiency": 1.0,
            },
        }

    def test_canvas_nodes_build_existing_analysis_model(self) -> None:
        setup = setup_from_canvas(
            "Defense",
            [
                {
                    "id": "solar",
                    "component": "Solar",
                    "quantity": 2,
                    "state": "Placed",
                    "zone": "External",
                },
                {
                    "id": "turret",
                    "component": "Turret",
                    "quantity": 3,
                    "state": "Planned",
                    "zone": "Defense",
                },
            ],
        )
        self.assertEqual(setup.name, "Defense")
        self.assertEqual(setup.components[0].quantity, 2)
        self.assertEqual(setup.components[1].zone, "Defense")

    def test_complete_source_to_load_path_is_not_reported_disconnected(self) -> None:
        nodes = [
            {"id": "s", "component": "Solar", "state": "Placed"},
            {"id": "b", "component": "Battery", "state": "Placed"},
            {"id": "t", "component": "Turret", "state": "Placed"},
        ]
        connections = [
            {"id": "1", "source": "s", "target": "b"},
            {"id": "2", "source": "b", "target": "t"},
        ]
        suggestions = circuit_recommendations(nodes, connections, self.catalog)
        combined = " ".join(suggestions).lower()
        self.assertNotIn("no complete source-to-load path", combined)
        self.assertNotIn("connect power into", combined)

    def test_cycle_is_reported(self) -> None:
        nodes = [
            {"id": "s", "component": "Solar", "state": "Placed"},
            {"id": "b", "component": "Battery", "state": "Placed"},
        ]
        connections = [
            {"id": "1", "source": "s", "target": "b"},
            {"id": "2", "source": "b", "target": "s"},
        ]
        suggestions = circuit_recommendations(nodes, connections, self.catalog)
        self.assertTrue(any("loop" in suggestion.lower() for suggestion in suggestions))

    def test_map_hotfix_removes_user_sliders(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "rust_companion_plus" / "ui" / "tabs" / "map_tab.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("self.opacity_slider", source)
        self.assertNotIn("self.blur_slider", source)
        self.assertIn("HEATMAP_OPACITY = 1.0", source)
        self.assertIn("Show server icons", source)


if __name__ == "__main__":
    unittest.main()
