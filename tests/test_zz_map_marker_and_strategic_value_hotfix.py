from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path

import rust_companion_plus.hotfix_map_shop as hotfix
from rust_companion_plus.services.shop_value import (
    score_shop_rows,
    sort_scored_rows,
)


@dataclass
class Offer:
    item_id: int = 634478325
    currency_id: int = -932201673
    quantity: int = 1
    cost: int = 50
    stock: int = 5
    shop: str = "Camera Shop"
    item_name: str = "CCTV Camera"
    currency_name: str = "Scrap"
    grid: str = "H12"
    x: float = 2000.0
    y: float = 2000.0
    item_is_blueprint: bool = False
    currency_is_blueprint: bool = False

    @property
    def shop_key(self) -> str:
        return f"{self.shop}|{self.grid}"


class StrategicShopValueHotfixTests(unittest.TestCase):
    def test_cctv_for_fifty_scrap_is_at_least_good_value(self) -> None:
        rows = [
            Offer(shop="Shop A", cost=50),
            Offer(shop="Shop B", cost=50),
            Offer(shop="Shop C", cost=50),
        ]
        scored, _ = score_shop_rows(rows)
        best = sort_scored_rows(scored, "Best value")[0]
        self.assertEqual("GOOD VALUE", best.deal.label)
        self.assertGreaterEqual(best.deal.score, 76)
        self.assertGreaterEqual(best.deal.discount_fraction, 0.50)
        self.assertEqual("", best.deal.alert_level)
        self.assertIn("strategic utility reference", best.deal.reason)

    def test_strategic_floor_does_not_override_a_cheaper_cctv_offer(self) -> None:
        rows = [
            Offer(shop="Best Shop", cost=25),
            Offer(shop="Second Shop", cost=50),
            Offer(shop="Third Shop", cost=50),
        ]
        scored, _ = score_shop_rows(rows)
        by_shop = {item.row.shop: item for item in scored}
        self.assertEqual(1, by_shop["Best Shop"].deal.peer_rank)
        self.assertGreater(by_shop["Second Shop"].deal.peer_rank, 1)
        self.assertNotIn(
            "curated 100-Scrap strategic utility reference",
            by_shop["Second Shop"].deal.reason,
        )

    def test_blueprint_or_non_scrap_cctv_does_not_use_floor(self) -> None:
        blueprint, _ = score_shop_rows([Offer(item_is_blueprint=True)])
        non_scrap, _ = score_shop_rows(
            [Offer(currency_name="High Quality Metal", currency_id=317398316)]
        )
        self.assertNotIn("strategic utility reference", blueprint[0].deal.reason)
        self.assertNotIn("strategic utility reference", non_scrap[0].deal.reason)


class MapMarkerHitTestingHotfixTests(unittest.TestCase):
    def test_click_hits_standard_and_centered_coordinate_payloads(self) -> None:
        common = dict(
            click=(300.0, 300.0),
            map_size=1000,
            source_size=(1000, 1000),
            crop_box=(0, 0, 1000, 1000),
            output_size=(500, 500),
            label_size=(600, 600),
        )
        standard = hotfix.find_clicked_marker(
            [{"name": "Standard", "type": 3, "x": 500, "y": 500}],
            **common,
        )
        centered = hotfix.find_clicked_marker(
            [{"name": "Centered", "type": 8, "x": -100, "y": -100}],
            click=(250.0, 350.0),
            map_size=1000,
            source_size=(1000, 1000),
            crop_box=(0, 0, 1000, 1000),
            output_size=(500, 500),
            label_size=(600, 600),
        )
        self.assertIsNotNone(standard)
        self.assertIsNotNone(centered)
        self.assertEqual("Standard", standard[0]["name"])
        self.assertEqual("Centered", centered[0]["name"])

    def test_zoom_crop_ignores_markers_outside_visible_area(self) -> None:
        hit = hotfix.find_clicked_marker(
            [{"name": "Far corner", "type": 3, "x": 50, "y": 950}],
            click=(250.0, 250.0),
            map_size=1000,
            source_size=(1000, 1000),
            crop_box=(250, 250, 750, 750),
            output_size=(500, 500),
            label_size=(500, 500),
        )
        self.assertIsNone(hit)


class HotfixActivationContractTests(unittest.TestCase):
    def test_both_entrypoints_activate_hotfix_before_startup(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in ("main.py", "launcher.py"):
            source = (root / relative).read_text(encoding="utf-8")
            self.assertIn("import rust_companion_plus.hotfix_map_shop", source)


if __name__ == "__main__":
    unittest.main()
