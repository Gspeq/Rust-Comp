from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from rust_companion_plus.services.profile_retention import (
    delete_all_saved_profiles,
    delete_saved_profile,
    purge_expired_profiles,
)
from rust_companion_plus.services.resource_heatmaps import ResourceHeatmapBundle
from rust_companion_plus.services.shop_value import score_shop_rows, sort_scored_rows
from rust_companion_plus.services.starter_spot import recommend_starter_spots
from rust_companion_plus.storage import JsonStore
from rust_companion_plus.ui.tabs.map_enhanced import ZOOM_LEVELS, zoom_crop
from rust_companion_plus.ui.tabs.smart_devices import normalize_devices


@dataclass(frozen=True)
class Offer:
    item_id: int
    currency_id: int
    quantity: int
    cost: int
    stock: int
    shop: str
    item_name: str = "Metal Fragments"
    grid: str = "A1"
    item_is_blueprint: bool = False
    currency_is_blueprint: bool = False


class ProfileRetentionTests(unittest.TestCase):
    def test_monthly_purge_removes_only_expired_profiles_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = JsonStore(root / "store.json")
            asset_root = root / "profiles"
            now = datetime(2026, 7, 22, tzinfo=timezone.utc)
            old_key = "old:28015"
            fresh_key = "fresh:28015"
            old_dir = asset_root / "old-profile"
            old_dir.mkdir(parents=True)
            (old_dir / "map.png").write_bytes(b"map")
            store.set(
                "saved_server_profiles",
                {
                    old_key: {
                        "key": old_key,
                        "saved_at": (now - timedelta(days=31)).isoformat(),
                        "assets": {"map_image_path": str(old_dir / "map.png")},
                    },
                    fresh_key: {
                        "key": fresh_key,
                        "saved_at": (now - timedelta(days=5)).isoformat(),
                    },
                },
            )
            store.set(
                "credential_profiles",
                {old_key: {"host": "old"}, fresh_key: {"host": "fresh"}},
            )
            removed = purge_expired_profiles(
                store,
                now=now,
                asset_root=asset_root,
            )
            self.assertEqual([old_key], removed)
            self.assertIsNone(
                (store.get("saved_server_profiles") or {}).get(old_key)
            )
            self.assertIn(fresh_key, store.get("saved_server_profiles"))
            self.assertNotIn(old_key, store.get("credential_profiles"))
            self.assertFalse(old_dir.exists())

    def test_remove_one_and_remove_all(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = JsonStore(root / "store.json")
            store.set(
                "saved_server_profiles",
                {
                    "one": {"key": "one"},
                    "two": {"key": "two"},
                },
            )
            self.assertTrue(
                delete_saved_profile(store, "one", asset_root=root / "assets")
            )
            self.assertEqual(
                ["two"],
                delete_all_saved_profiles(store, asset_root=root / "assets"),
            )
            self.assertEqual({}, store.get("saved_server_profiles"))


class StarterSpotTests(unittest.TestCase):
    def test_recommendation_selects_resource_access_away_from_monument(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stone = Image.new("L", (72, 72), 0)
            road = Image.new("L", (72, 72), 0)
            monument = Image.new("L", (72, 72), 0)
            ImageDraw.Draw(stone).ellipse((12, 18, 32, 38), fill=255)
            ImageDraw.Draw(road).ellipse((14, 20, 34, 40), fill=220)
            ImageDraw.Draw(monument).ellipse((50, 10, 70, 30), fill=255)
            paths = {}
            for name, image in (
                ("Stone", stone),
                ("Road Access", road),
                ("Monument Proximity", monument),
            ):
                path = root / f"{name}.png"
                image.save(path)
                paths[name] = [path]
            bundle = ResourceHeatmapBundle(
                source_root=root,
                raster_layers=paths,
                detected_world_size=4000,
            )
            spots = recommend_starter_spots(bundle, 4000, limit=3, resolution=72)
            self.assertTrue(spots)
            self.assertGreaterEqual(spots[0].score, spots[-1].score)
            self.assertTrue(spots[0].grid)
            self.assertTrue(any("stone" in reason for reason in spots[0].reasons))


class MarketplaceValueTests(unittest.TestCase):
    def test_best_value_is_visible_and_places_cheapest_unit_trade_first(self) -> None:
        rows = [
            Offer(1, 2, 100, 50, 20, "Cheap"),
            Offer(1, 2, 100, 100, 20, "Normal"),
            Offer(1, 2, 100, 150, 20, "High"),
        ]
        scored, _history = score_shop_rows(rows)
        ordered = sort_scored_rows(scored, "Best value")
        self.assertEqual("Cheap", ordered[0].row.shop)
        self.assertGreater(ordered[0].deal.score, ordered[-1].deal.score)
        self.assertIn(ordered[0].deal.label, {"STEAL", "CAN'T MISS", "GOOD VALUE"})


class HubContractTests(unittest.TestCase):
    def test_zoom_is_bounded_and_published(self) -> None:
        image = Image.new("RGBA", (400, 300), (1, 2, 3, 255))
        zoomed = zoom_crop(image, 4.0, (0.0, 0.0))
        self.assertEqual(image.size, zoomed.size)
        self.assertEqual(
            ("Fit", "1.5x", "2x", "3x", "4x", "6x", "8x"),
            ZOOM_LEVELS,
        )

    def test_smart_devices_deduplicate_and_favorite_first(self) -> None:
        rows = normalize_devices(
            [
                {"entity_id": 2, "name": "Door"},
                {"entity_id": "1", "name": "Alarm", "favorite": True},
                {"entity_id": 2, "name": "Duplicate"},
                {"entity_id": "not-an-id", "name": "Invalid"},
            ]
        )
        self.assertEqual([1, 2], [row["entity_id"] for row in rows])

    def test_application_uses_the_new_hubs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app = (root / "rust_companion_plus" / "app.py").read_text(encoding="utf-8")
        tools = (
            root / "rust_companion_plus" / "ui" / "tabs" / "tools.py"
        ).read_text(encoding="utf-8")
        bootstrap = (root / "rust_companion_plus" / "bootstrap.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("map_enhanced", app)
        self.assertIn("shops_enhanced", app)
        self.assertIn("electrical_hub", app)
        self.assertIn('"Smart Devices":', app)
        self.assertIn('"Saved Servers":', app)
        self.assertNotIn('"Utilities":', app)
        self.assertNotIn("ToolsTab", app)
        self.assertEqual(0, app.count('text="NAVIGATION"'))
        self.assertNotIn("Grid & Distance", tools)
        self.assertNotIn('tabs.add("Smart Devices")', tools)
        self.assertNotIn("def _devices", tools)
        self.assertIn("purge_expired_profiles", bootstrap)
        self.assertIn("delete_all_saved_profiles", bootstrap)

    def test_shop_and_electrical_simple_advanced_contracts(self) -> None:
        root = Path(__file__).resolve().parents[1]
        shop = (
            root / "rust_companion_plus" / "ui" / "tabs" / "shops_enhanced.py"
        ).read_text(encoding="utf-8")
        electrical = (
            root / "rust_companion_plus" / "ui" / "tabs" / "electrical_hub.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"Best value"', shop)
        self.assertIn('tabs.add("Simple")', shop)
        self.assertIn('tabs.add("Advanced")', shop)
        self.assertNotIn("Simple Planner", electrical)
        self.assertNotIn("CTkTabview", electrical)
        self.assertIn("AdvancedElectricalTab", electrical)


if __name__ == "__main__":
    unittest.main()
