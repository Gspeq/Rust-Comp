from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rust_companion_plus.app import RustCompanionApp
from rust_companion_plus.services.item_catalog import (
    RustItemCatalog,
    parse_item_catalog,
)
from rust_companion_plus.ui.tabs.shops import (
    ShopFilters,
    collect_shop_rows,
    rust_grid_reference,
)


class ShopGridAndDesignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.labels = {
            100: "Assault Rifle",
            200: "Scrap",
            300: "Sulfur",
            400: "Metal Fragments",
        }
        self.markers = [
            {
                "type": 3,
                "name": "Outpost Guns",
                "x": 1000,
                "y": 1000,
                "sell_orders": [
                    {
                        "item_id": 100,
                        "quantity": 1,
                        "currency_id": 200,
                        "cost_per_item": 500,
                        "amount_in_stock": 3,
                        "item_is_blueprint": False,
                        "currency_is_blueprint": False,
                    },
                    {
                        "item_id": 300,
                        "quantity": 1000,
                        "currency_id": 400,
                        "cost_per_item": 50,
                        "amount_in_stock": 0,
                        "item_is_blueprint": False,
                        "currency_is_blueprint": False,
                    },
                ],
            },
            {
                "type": 3,
                "name": "Blueprint Shop",
                "x": 800,
                "y": 900,
                "sell_orders": [
                    {
                        "item_id": 100,
                        "quantity": 1,
                        "currency_id": 300,
                        "cost_per_item": 25,
                        "amount_in_stock": 8,
                        "item_is_blueprint": True,
                        "currency_is_blueprint": False,
                    }
                ],
            },
        ]

    def label(self, item_id):
        return self.labels.get(int(item_id), f"Item {item_id}")

    def search_text(self, item_id):
        return f"{self.label(item_id)} {item_id}".casefold()

    def rows(self, **kwargs):
        return collect_shop_rows(
            self.markers,
            map_size=3800,
            label=self.label,
            search_text=self.search_text,
            filters=ShopFilters(**kwargs),
        )

    def test_split_refresh_keeps_one_second_death_accuracy(self) -> None:
        self.assertEqual(
            5_000,
            RustCompanionApp.RUSTPLUS_INTERVAL_MS,
        )
        self.assertEqual(
            1_000,
            RustCompanionApp.TEAM_INTERVAL_MS,
        )

    def test_official_rustplus_grid_conversion(self) -> None:
        self.assertEqual(
            "G19",
            rust_grid_reference(1000, 1000, 3800),
        )

    def test_grid_and_coordinates_are_in_result(self) -> None:
        rows = self.rows(location_query="G19")
        self.assertEqual(2, len(rows))
        self.assertEqual("G19", rows[0].grid)
        self.assertEqual("1000, 1000", rows[0].coordinates)
        self.assertIn("G19", rows[0].trade_sentence)

    def test_buy_search_matches_item_being_sold(self) -> None:
        rows = self.rows(buy_query="assault")
        self.assertEqual(2, len(rows))
        self.assertTrue(
            all(row.item_id == 100 for row in rows)
        )

    def test_sell_search_matches_currency_shop_wants(self) -> None:
        rows = self.rows(sell_query="scrap")
        self.assertEqual(1, len(rows))
        self.assertEqual(200, rows[0].currency_id)

    def test_stock_price_blueprint_filters(self) -> None:
        rows = self.rows(
            in_stock_only=True,
            max_cost=100,
            blueprint_mode="Sells blueprint",
        )
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual(25, row.cost)
        self.assertEqual("Sells BP", row.offer_type)

    def test_grid_sort(self) -> None:
        rows = self.rows(sort_mode="Grid")
        grids = [row.grid for row in rows]
        self.assertEqual(sorted(grids), grids)

    def test_item_catalog_parses_names_and_shortnames(self) -> None:
        entries = parse_item_catalog(
            {
                "items": [
                    {
                        "itemId": 100,
                        "displayName": {
                            "english": "Assault Rifle"
                        },
                        "shortname": "rifle.ak",
                    }
                ]
            }
        )
        self.assertEqual(
            "Assault Rifle",
            entries[100].name,
        )
        self.assertEqual(
            "rifle.ak",
            entries[100].shortname,
        )

    def test_item_catalog_caches_and_searches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "items.json"
            catalog = RustItemCatalog(
                cache_path=cache,
                fetch_json=lambda _url: [
                    {
                        "id": 200,
                        "name": "Scrap",
                        "shortName": "scrap",
                    }
                ],
            )
            self.assertEqual(1, catalog.load(force=True))
            self.assertEqual("Scrap", catalog.label(200))
            self.assertIn(
                "scrap",
                catalog.search_text(200),
            )
            saved = json.loads(
                cache.read_text(encoding="utf-8")
            )
            self.assertEqual(
                "Scrap",
                saved["items"]["200"]["name"],
            )


if __name__ == "__main__":
    unittest.main()
