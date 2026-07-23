from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from rust_companion_plus.services.electrical_canvas import (
    ASSUMPTION_HELP_TEXT,
    ELECTRICAL_ZOOM_LEVELS,
    graph_layout_positions,
    orthogonal_connection_points,
)
from rust_companion_plus.services.shop_grid_map import (
    SHOP_GRID_SPAN,
    render_selected_shop_grid,
    shop_grid_viewport,
)
from rust_companion_plus.services.shop_value import (
    item_value_profile,
    score_shop_rows,
    sort_scored_rows,
)


@dataclass
class Offer:
    item_id: int
    currency_id: int
    quantity: int
    cost: int
    stock: int
    shop: str
    item_name: str
    currency_name: str
    grid: str = "A1"
    x: float = 1000.0
    y: float = 3000.0
    item_is_blueprint: bool = False
    currency_is_blueprint: bool = False

    @property
    def shop_key(self) -> str:
        return f"{self.shop}|{self.grid}"


class ElectricalCanvasPrecisionTests(unittest.TestCase):
    def test_orthogonal_routes_use_right_angles_and_avoid_obstacle(self) -> None:
        nodes = [
            {"id": "source", "x": 20, "y": 120},
            {"id": "obstacle", "x": 300, "y": 90},
            {"id": "target", "x": 600, "y": 120},
        ]
        coords = orthogonal_connection_points(
            nodes,
            {"source": "source", "target": "target"},
            node_width=166,
            node_height=68,
        )
        self.assertIsNotNone(coords)
        points = list(zip(coords[0::2], coords[1::2]))
        for start, end in zip(points, points[1:]):
            self.assertTrue(
                start[0] == end[0] or start[1] == end[1],
                (start, end),
            )
        obstacle = (282, 72, 484, 176)
        for start, end in zip(points, points[1:]):
            if start[0] == end[0]:
                x = start[0]
                low, high = sorted((start[1], end[1]))
                self.assertFalse(
                    obstacle[0] < x < obstacle[2]
                    and max(low, obstacle[1]) < min(high, obstacle[3])
                )
            else:
                y = start[1]
                low, high = sorted((start[0], end[0]))
                self.assertFalse(
                    obstacle[1] < y < obstacle[3]
                    and max(low, obstacle[0]) < min(high, obstacle[2])
                )

    def test_graph_arrange_follows_real_power_flow(self) -> None:
        nodes = [
            {"id": "wind", "component": "Wind Turbine", "zone": "Main"},
            {"id": "root", "component": "Root Combiner", "zone": "Main"},
            {"id": "branch", "component": "Electrical Branch", "zone": "Main"},
            {"id": "turret", "component": "Auto Turret", "zone": "Defense"},
        ]
        connections = [
            {"source": "wind", "target": "root"},
            {"source": "root", "target": "branch"},
            {"source": "branch", "target": "turret"},
        ]
        catalog = {
            "Wind Turbine": {"category": "generation"},
            "Root Combiner": {"category": "logic"},
            "Electrical Branch": {"category": "control"},
            "Auto Turret": {"category": "load"},
        }
        positions = graph_layout_positions(nodes, connections, catalog)
        self.assertLess(positions["wind"][0], positions["root"][0])
        self.assertLess(positions["root"][0], positions["branch"][0])
        self.assertLess(positions["branch"][0], positions["turret"][0])

    def test_assumption_help_and_zoom_contract(self) -> None:
        self.assertIn("Solar average %", ASSUMPTION_HELP_TEXT)
        self.assertIn("Wind average %", ASSUMPTION_HELP_TEXT)
        self.assertIn("Battery charge %", ASSUMPTION_HELP_TEXT)
        self.assertEqual(0.50, ELECTRICAL_ZOOM_LEVELS[0])
        self.assertEqual(2.00, ELECTRICAL_ZOOM_LEVELS[-1])
        self.assertIn(1.00, ELECTRICAL_ZOOM_LEVELS)


class ShopGridNeighborhoodTests(unittest.TestCase):
    def test_shop_map_uses_aligned_two_by_two_neighborhood(self) -> None:
        viewport = shop_grid_viewport(
            (1000, 1000),
            1000,
            3000,
            4000,
        )
        self.assertEqual(2, SHOP_GRID_SPAN)
        self.assertEqual(2, viewport.span)
        width = viewport.crop_box[2] - viewport.crop_box[0]
        height = viewport.crop_box[3] - viewport.crop_box[1]
        expected_cell = 1000 / viewport.grid_count
        self.assertAlmostEqual(width, expected_cell * 2, delta=3)
        self.assertAlmostEqual(height, expected_cell * 2, delta=3)
        self.assertTrue(0.0 <= viewport.marker_fraction[0] <= 1.0)
        self.assertTrue(0.0 <= viewport.marker_fraction[1] <= 1.0)

    def test_rendered_shop_marker_uses_true_position_not_forced_center(self) -> None:
        base = Image.new("RGBA", (1000, 1000), (20, 30, 40, 255))
        selected = Offer(
            1,
            2,
            1,
            10,
            1,
            "Test Shop",
            "Rocket",
            "Scrap",
            grid="G6",
            x=1111,
            y=2888,
        )
        viewport = shop_grid_viewport(base.size, selected.x, selected.y, 4000)
        rendered = render_selected_shop_grid(
            base,
            selected,
            4000,
            output_size=(240, 240),
        )
        expected_x = round(viewport.marker_fraction[0] * 240)
        expected_y = round(viewport.marker_fraction[1] * 240)
        orange = []
        for y in range(max(0, expected_y - 18), min(240, expected_y + 19)):
            for x in range(max(0, expected_x - 18), min(240, expected_x + 19)):
                if rendered.getpixel((x, y))[:3] == (245, 158, 11):
                    orange.append((x, y))
        self.assertTrue(orange)


class MarketplaceCalibrationTests(unittest.TestCase):
    def _offers(
        self,
        item: str,
        currency: str,
        costs: list[int],
        *,
        shops: list[str] | None = None,
        blueprint: bool = False,
    ) -> list[Offer]:
        names = shops or [f"Shop {index}" for index in range(len(costs))]
        return [
            Offer(
                100,
                200,
                1,
                cost,
                8,
                names[index],
                item,
                currency,
                item_is_blueprint=blueprint,
            )
            for index, cost in enumerate(costs)
        ]

    def test_rocket_launcher_is_high_tier_not_endgame_rocket(self) -> None:
        profile = item_value_profile("Rocket Launcher")
        self.assertEqual(3, profile.tier)
        self.assertEqual("High tier", profile.tier_name)
        self.assertEqual(4, item_value_profile("Rocket").tier)

    def test_duplicate_listings_from_one_shop_do_not_inflate_confidence(self) -> None:
        rows = self._offers(
            "Assault Rifle",
            "Scrap",
            [100, 500, 510, 520],
            shops=["Same Shop", "Same Shop", "Same Shop", "Other Shop"],
        )
        scored, _ = score_shop_rows(rows)
        best = sort_scored_rows(scored, "Best value")[0]
        self.assertEqual(2, best.deal.unique_shop_count)
        self.assertNotEqual("High", best.deal.confidence)

    def test_early_items_never_become_steals(self) -> None:
        scored, _ = score_shop_rows(
            self._offers("Revolver", "Scrap", [10, 200, 220, 240])
        )
        best = sort_scored_rows(scored, "Best value")[0]
        self.assertIn(best.deal.label, {"GOOD VALUE", "FAIR"})
        self.assertFalse(best.deal.actionable)

    def test_ordinary_component_needs_extreme_discount_for_steal(self) -> None:
        ordinary, _ = score_shop_rows(
            self._offers("Gears", "Scrap", [70, 100, 105, 110])
        )
        extreme, _ = score_shop_rows(
            self._offers("Gears", "Scrap", [15, 100, 105, 110])
        )
        ordinary_best = sort_scored_rows(ordinary, "Best value")[0]
        extreme_best = sort_scored_rows(extreme, "Best value")[0]
        self.assertNotIn(ordinary_best.deal.label, {"STEAL", "CAN'T MISS"})
        self.assertEqual("STEAL", extreme_best.deal.label)

    def test_blueprint_burden_blocks_borderline_cant_miss(self) -> None:
        normal, _ = score_shop_rows(
            self._offers("Assault Rifle", "Scrap", [100, 500, 550, 600])
        )
        blueprint, _ = score_shop_rows(
            self._offers(
                "Assault Rifle",
                "Scrap",
                [100, 500, 550, 600],
                blueprint=True,
            )
        )
        normal_best = sort_scored_rows(normal, "Best value")[0]
        bp_best = sort_scored_rows(blueprint, "Best value")[0]
        self.assertGreaterEqual(normal_best.deal.score, bp_best.deal.score)
        self.assertGreater(bp_best.deal.blueprint_penalty, 0)


class PrecisionSourceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def test_electrical_has_help_zoom_and_orthogonal_wires(self) -> None:
        electrical = self.read("rust_companion_plus/ui/tabs/electrical.py")
        self.assertIn("show_assumption_help", electrical)
        self.assertIn("ASSUMPTION_HELP_TEXT", electrical)
        self.assertIn("step_canvas_zoom", electrical)
        self.assertIn("orthogonal_connection_points", electrical)
        self.assertIn("graph_layout_positions", electrical)
        self.assertNotIn("smooth=True", electrical)

    def test_main_map_fetches_real_clean_and_icon_variants(self) -> None:
        map_source = self.read(
            "rust_companion_plus/ui/tabs/map_tab.py"
        )
        client_source = self.read(
            "rust_companion_plus/services/rustplus_client.py"
        )
        # The UI intentionally requests both images through one Rust+ session.
        self.assertIn(
            "self.context.rust.fetch_map_variants(",
            map_source,
        )
        self.assertNotIn(
            "self.context.rust.fetch_clean_map(",
            map_source,
        )
        self.assertIn("icon_image", map_source)
        self.assertIn("clean_image", map_source)
        self.assertIn(
            "self.context.clean_map_image = clean_image.copy()",
            map_source,
        )
        self.assertIn(
            "self.map_image_with_icons = icon_image.copy()",
            map_source,
        )
        # The client owns the lower-level clean and icon-rendered requests.
        self.assertIn("def fetch_clean_map", client_source)
        self.assertIn("def fetch_map_variants", client_source)
        self.assertIn("add_icons=False", client_source)
        self.assertIn("add_icons=True", client_source)
        self.assertIn("add_vending_machines=False", client_source)
        self.assertIn("add_vending_machines=True", client_source)

    def test_shop_and_guide_describe_two_by_two_map(self) -> None:
        shops = self.read("rust_companion_plus/ui/tabs/shops.py")
        guide = self.read("rust_companion_plus/services/guide_catalog.py")
        self.assertIn("2×2", shops)
        self.assertIn("2×2", guide)
        self.assertIn('GUIDE_VERSION = "0.8.2"', guide)

    def test_shop_title_is_updated_for_initial_and_cleared_states(self) -> None:
        shops = self.read("rust_companion_plus/ui/tabs/shops.py")
        self.assertNotIn('text="Item shop minimap"', shops)
        self.assertNotIn(
            'self.minimap_title.configure(text="Item shop minimap")',
            shops,
        )
        self.assertIn('text="2×2 shop area"', shops)
        self.assertIn(
            'self.minimap_title.configure(text="2×2 shop area")',
            shops,
        )

    def test_marketplace_source_uses_unique_shop_evidence(self) -> None:
        source = self.read("rust_companion_plus/services/shop_value.py")
        self.assertIn("unique_shop_count", source)
        self.assertIn("market_spread", source)
        self.assertIn("blueprint_penalty", source)
        self.assertIn("HISTORY_VERSION = 4", source)


if __name__ == "__main__":
    unittest.main()
