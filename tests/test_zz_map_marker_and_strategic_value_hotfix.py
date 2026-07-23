from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

import rust_companion_plus.hotfix_map_shop as hotfix
from rust_companion_plus.services.shop_value import score_shop_rows, sort_scored_rows


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


class MapLayerRenderingHotfixTests(unittest.TestCase):
    def test_raster_heatmap_is_made_visible(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            mask_path = Path(folder) / "heatmap_sulfur.png"
            mask = Image.new("L", (64, 64), 0)
            ImageDraw.Draw(mask).ellipse((18, 18, 46, 46), fill=145)
            mask.save(mask_path)
            bundle = SimpleNamespace(
                points={},
                raster_layers={"Sulfur": [mask_path]},
                source_root=Path(folder),
            )
            base = Image.new("RGBA", (128, 128), (25, 35, 45, 255))
            rendered, diagnostics = hotfix.composite_visible_heatmaps(
                base, bundle, ["Sulfur"]
            )
            self.assertEqual((0, 1), diagnostics["Sulfur"])
            self.assertNotEqual(base.getpixel((64, 64)), rendered.getpixel((64, 64)))
            self.assertGreater(rendered.getpixel((64, 64))[0], base.getpixel((64, 64))[0])

    def test_server_markers_are_drawn_without_alternate_map_image(self) -> None:
        base = Image.new("RGBA", (200, 200), (20, 30, 40, 255))
        marker = {
            "id": "shop-1",
            "type": 3,
            "x": 500,
            "y": 500,
            "name": "Sulfur Shop",
            "sell_orders": [{"item_id": 1}],
        }
        rendered, positions = hotfix.render_server_markers(base, [marker], 1000)
        self.assertEqual(1, len(positions))
        x, y = positions[0]["pixel"]
        self.assertAlmostEqual(100, x, delta=1)
        self.assertAlmostEqual(100, y, delta=1)
        self.assertNotEqual(base.getpixel((x, y)), rendered.getpixel((x, y)))
        self.assertEqual("$", hotfix.marker_visual(marker)[1])

    def test_composition_order_keeps_marker_above_heatmap(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            mask_path = Path(folder) / "heatmap_sulfur.png"
            Image.new("L", (100, 100), 255).save(mask_path)
            bundle = SimpleNamespace(
                points={},
                raster_layers={"Sulfur": [mask_path]},
                source_root=Path(folder),
            )
            base = Image.new("RGBA", (100, 100), (30, 30, 30, 255))
            marker = {"type": 3, "x": 500, "y": 500, "name": "Shop"}
            rendered, diagnostics, positions = hotfix.compose_map_layers(
                base,
                bundle,
                ["Sulfur"],
                [marker],
                1000,
                show_server_icons=True,
            )
            self.assertEqual((0, 1), diagnostics["Sulfur"])
            self.assertEqual(1, len(positions))
            center = positions[0]["pixel"]
            self.assertGreater(rendered.getpixel(center)[1], 120)


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
            click=(249.8, 350.2),
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



class DroneMarketplaceFilterHotfixTests(unittest.TestCase):
    def test_player_owned_vending_is_a_drone_marketplace_candidate(self) -> None:
        marker = {
            "type": 3,
            "steam_id": 76561198000000000,
            "name": "Sulfur for Scrap",
            "sell_orders": [{"item_id": 1}],
        }
        self.assertTrue(hotfix.is_drone_marketplace_marker(marker))

    def test_npc_vending_without_owner_is_not_in_drone_only_view(self) -> None:
        marker = {
            "type": 3,
            "steam_id": 0,
            "name": "Outpost Components",
            "sell_orders": [{"item_id": 1}],
        }
        self.assertFalse(hotfix.is_drone_marketplace_marker(marker))

    def test_explicit_drone_flag_is_supported(self) -> None:
        marker = {
            "type": 3,
            "steam_id": 0,
            "drone_only": True,
            "sell_orders": [{"item_id": 1}],
        }
        self.assertTrue(hotfix.is_drone_marketplace_marker(marker))

    def test_filter_keeps_only_drone_marketplace_markers(self) -> None:
        markers = [
            {"id": "player", "type": 3, "steam_id": 123, "sell_orders": [{}]},
            {"id": "npc", "type": 3, "steam_id": 0, "sell_orders": [{}]},
            {"id": "event", "type": 8, "steam_id": 123},
        ]
        filtered = hotfix.filter_drone_marketplace_markers(markers)
        self.assertEqual(["player"], [row["id"] for row in filtered])


class AppErrorNotificationHotfixTests(unittest.TestCase):
    def setUp(self) -> None:
        hotfix._ERROR_LAST_SENT.clear()

    def test_relevant_errors_are_selected(self) -> None:
        self.assertTrue(
            hotfix.is_relevant_app_error(
                "Map analysis",
                RuntimeError("Parser crashed while loading the current map"),
            )
        )
        self.assertFalse(
            hotfix.is_relevant_app_error(
                "Pairing",
                RuntimeError("Complete the Rust+ credentials first"),
            )
        )

    def test_identical_error_is_not_spammed_during_cooldown(self) -> None:
        with mock.patch.object(
            hotfix,
            "show_windows_notification",
            return_value=True,
        ) as native:
            first = hotfix.publish_relevant_app_error(
                None,
                "Map refresh",
                RuntimeError("Map parser failed"),
            )
            second = hotfix.publish_relevant_app_error(
                None,
                "Map refresh",
                RuntimeError("Map parser failed"),
            )
        self.assertTrue(first)
        self.assertFalse(second)
        native.assert_called_once()

    def test_background_thread_error_is_marshaled_to_tk_thread(self) -> None:
        callbacks = []
        published = []

        class Store:
            def __init__(self) -> None:
                self.values = {}

            def get(self, key, default=None):
                return self.values.get(key, default)

            def set(self, key, value) -> None:
                self.values[key] = value

        context = SimpleNamespace(
            store=Store(),
            record_event=lambda *args: None,
        )
        app = SimpleNamespace(
            context=context,
            deal_notifications=SimpleNamespace(
                publish=lambda *args, **kwargs: published.append((args, kwargs))
            ),
            after=lambda _delay, callback: callbacks.append(callback),
            show_tab=lambda _name: None,
        )
        worker = object()
        main = object()
        with mock.patch.object(hotfix.threading, "current_thread", return_value=worker), mock.patch.object(
            hotfix.threading, "main_thread", return_value=main
        ):
            delivered = hotfix.publish_relevant_app_error(
                app,
                "Background sync",
                RuntimeError("Socket worker crashed"),
            )

        self.assertTrue(delivered)
        self.assertEqual(1, len(callbacks))
        self.assertEqual([], published)
        callbacks[0]()
        self.assertEqual(1, len(published))


class HotfixActivationContractTests(unittest.TestCase):
    def test_central_bootstrap_activates_hotfix_before_gui_import(self) -> None:
        root = Path(__file__).resolve().parents[1]
        bootstrap = (root / "rust_companion_plus" / "bootstrap.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MAP_SHOP_HOTFIX_BOOTSTRAP_V2", bootstrap)
        self.assertIn("import rust_companion_plus.hotfix_map_shop", bootstrap)
        self.assertLess(
            bootstrap.index("import rust_companion_plus.hotfix_map_shop"),
            bootstrap.index("def launch_gui("),
        )

    def test_hotfix_replaces_enhanced_map_class(self) -> None:
        from rust_companion_plus.ui.tabs import map_enhanced

        self.assertIs(map_enhanced.MapTab, hotfix.ClickableServerMarkerMapTab)
        self.assertEqual(
            hotfix.HOTFIX_ID,
            map_enhanced._map_layers_hotfix_installed,
        )

    def test_hotfix_replaces_enhanced_shop_class(self) -> None:
        from rust_companion_plus.ui.tabs import shops_enhanced

        self.assertIs(
            shops_enhanced.ShopsTab,
            hotfix.DroneMarketplaceShopsTab,
        )
        self.assertEqual(
            hotfix.HOTFIX_ID,
            shops_enhanced._drone_filter_hotfix_installed,
        )

    def test_enhanced_shop_scoring_uses_strategic_wrapper(self) -> None:
        from rust_companion_plus.ui.tabs import shops_enhanced

        self.assertIs(
            shops_enhanced.score_shop_rows,
            hotfix.score_shop_rows_with_strategic_references,
        )

    def test_app_error_hook_is_installed(self) -> None:
        from rust_companion_plus import app

        self.assertEqual(
            hotfix.HOTFIX_ID,
            app.RustCompanionApp._error_notification_hotfix_installed,
        )


if __name__ == "__main__":
    unittest.main()
