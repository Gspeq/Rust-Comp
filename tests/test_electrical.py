from __future__ import annotations

import math
import unittest

from rust_companion_plus.models import ElectricalSetup, SetupComponent
from rust_companion_plus.services.electrical import analyze_setup, parse_component_text


class ParserTests(unittest.TestCase):
    def test_goal_parser(self) -> None:
        result = parse_component_text(
            "Power 6 auto turrets, 4 lights, 2 doors, and a large battery backup"
        )
        self.assertEqual(result.components["Auto Turret"], 6)
        self.assertEqual(result.components["Ceiling Light"], 4)
        self.assertEqual(result.components["Door Controller"], 2)
        self.assertEqual(result.components["Large Rechargeable Battery"], 1)


class AnalyzerTests(unittest.TestCase):
    def test_known_power_balance(self) -> None:
        setup = ElectricalSetup(
            components=[
                SetupComponent("Auto Turret", 6, "Planned"),
                SetupComponent("Ceiling Light", 4, "Planned"),
                SetupComponent("Door Controller", 2, "Planned"),
                SetupComponent("Large Rechargeable Battery", 1, "Planned"),
                SetupComponent("Wind Turbine", 1, "Planned"),
            ]
        )
        result = analyze_setup(setup)
        self.assertEqual(result.load_rw, 70)
        self.assertEqual(result.peak_generation_rw, 150)
        self.assertEqual(result.battery_capacity_rwm, 24000)
        self.assertAlmostEqual(result.no_generation_runtime_minutes, 24000 / 70)
        self.assertFalse(math.isinf(result.no_generation_runtime_minutes))

    def test_inventory_not_powered(self) -> None:
        setup = ElectricalSetup(
            components=[SetupComponent("Auto Turret", 10, "Inventory")]
        )
        result = analyze_setup(setup)
        self.assertEqual(result.load_rw, 0)


if __name__ == "__main__":
    unittest.main()
