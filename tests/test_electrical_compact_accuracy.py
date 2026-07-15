from __future__ import annotations

import ast
import math
import unittest
from pathlib import Path

from rust_companion_plus.catalog import electrical_catalog
from rust_companion_plus.models import ElectricalSetup, SetupComponent
from rust_companion_plus.services.electrical import analyze_setup
from rust_companion_plus.ui.tabs.electrical import (
    CONNECTOR_RADIUS,
    NODE_HEIGHT,
    NODE_WIDTH,
    circuit_recommendations,
)


ROOT = Path(__file__).resolve().parents[1]
ELECTRICAL_UI = ROOT / "rust_companion_plus" / "ui" / "tabs" / "electrical.py"


class ElectricalCatalogAccuracyTests(unittest.TestCase):
    def test_verified_generation_and_battery_values(self) -> None:
        catalog = electrical_catalog()

        self.assertEqual(catalog["Large Solar Panel"]["max_output"], 20)
        self.assertEqual(catalog["Wind Turbine"]["max_output"], 150)
        self.assertEqual(catalog["Small Generator"]["max_output"], 40)

        expected_batteries = {
            "Small Rechargeable Battery": (400, 15, 0.8),
            "Medium Rechargeable Battery": (9000, 50, 0.8),
            "Large Rechargeable Battery": (24000, 100, 0.8),
        }
        for name, (capacity, output, efficiency) in expected_batteries.items():
            row = catalog[name]
            self.assertEqual(row["capacity_rwm"], capacity)
            self.assertEqual(row["output_limit"], output)
            self.assertAlmostEqual(row["charge_efficiency"], efficiency)

    def test_corrected_component_draw_values(self) -> None:
        catalog = electrical_catalog()
        self.assertEqual(catalog["Fluorescent Light"]["power_draw"], 1)
        self.assertEqual(catalog["Smart Switch"]["power_draw"], 0)
        self.assertEqual(catalog["Electrical Branch"]["power_draw"], 0)


class ElectricalMathAccuracyTests(unittest.TestCase):
    def test_battery_input_efficiency_applies_to_average_generation(self) -> None:
        setup = ElectricalSetup(
            components=[
                SetupComponent("Auto Turret", 1, "Planned"),
                SetupComponent("Large Solar Panel", 1, "Planned"),
                SetupComponent("Small Rechargeable Battery", 1, "Planned"),
            ],
            assumptions={
                "solar_utilization": 0.50,
                "wind_utilization": 0.55,
                "battery_charge_fraction": 1.0,
            },
        )

        result = analyze_setup(setup)

        self.assertEqual(result.load_rw, 10)
        self.assertEqual(result.estimated_generation_rw, 10)
        self.assertEqual(result.usable_generation_rw, 8)
        self.assertEqual(result.battery_charge_efficiency, 0.8)
        self.assertEqual(result.no_generation_runtime_minutes, 40)
        self.assertEqual(result.estimated_runtime_minutes, 200)
        self.assertEqual(result.required_peak_for_charging_rw, 12.5)

    def test_generation_without_storage_is_not_penalized(self) -> None:
        setup = ElectricalSetup(
            components=[
                SetupComponent("Auto Turret", 1, "Planned"),
                SetupComponent("Large Solar Panel", 1, "Planned"),
            ],
            assumptions={
                "solar_utilization": 0.50,
                "wind_utilization": 0.55,
                "battery_charge_fraction": 1.0,
            },
        )

        result = analyze_setup(setup)

        self.assertEqual(result.estimated_generation_rw, 10)
        self.assertEqual(result.usable_generation_rw, 10)
        self.assertEqual(result.battery_charge_efficiency, 1.0)
        self.assertTrue(math.isinf(result.estimated_runtime_minutes))

    def test_medium_to_large_battery_swap_is_suggested(self) -> None:
        setup = ElectricalSetup(
            components=[
                SetupComponent("Auto Turret", 5, "Planned"),
                SetupComponent("Medium Rechargeable Battery", 2, "Planned"),
                SetupComponent("Wind Turbine", 1, "Planned"),
            ]
        )

        recommendations = " ".join(analyze_setup(setup).recommendations).lower()
        self.assertIn("one large battery", recommendations)
        self.assertIn("18,000", recommendations)
        self.assertIn("24,000", recommendations)

    def test_large_solar_array_can_suggest_wind_swap(self) -> None:
        setup = ElectricalSetup(
            components=[
                SetupComponent("Auto Turret", 5, "Planned"),
                SetupComponent("Large Solar Panel", 8, "Planned"),
                SetupComponent("Large Rechargeable Battery", 1, "Planned"),
            ]
        )

        recommendations = " ".join(analyze_setup(setup).recommendations).lower()
        self.assertIn("well-elevated wind turbine", recommendations)


class CompactElectricalUiTests(unittest.TestCase):
    def test_nodes_are_compact(self) -> None:
        self.assertLessEqual(NODE_WIDTH, 170)
        self.assertLessEqual(NODE_HEIGHT, 70)
        self.assertLessEqual(CONNECTOR_RADIUS, 5)

    def test_ctk_buttons_do_not_receive_justify(self) -> None:
        source = ELECTRICAL_UI.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(ELECTRICAL_UI))
        offenders: list[int] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "CTkButton"
                and isinstance(func.value, ast.Name)
                and func.value.id == "ctk"
            ):
                continue
            offenders.extend(
                keyword.lineno
                for keyword in node.keywords
                if keyword.arg == "justify"
            )

        self.assertEqual(offenders, [])

    def test_splitter_with_uneven_direct_loads_suggests_branch(self) -> None:
        catalog = electrical_catalog()
        nodes = [
            {"id": "source", "component": "Large Rechargeable Battery", "state": "Placed"},
            {"id": "split", "component": "Splitter", "state": "Placed"},
            {"id": "turret", "component": "Auto Turret", "state": "Placed"},
            {"id": "door", "component": "Door Controller", "state": "Placed"},
        ]
        connections = [
            {"id": "1", "source": "source", "target": "split"},
            {"id": "2", "source": "split", "target": "turret"},
            {"id": "3", "source": "split", "target": "door"},
        ]

        recommendations = " ".join(
            circuit_recommendations(nodes, connections, catalog)
        ).lower()
        self.assertIn("electrical branch", recommendations)
        self.assertIn("divide evenly", recommendations)


if __name__ == "__main__":
    unittest.main()
