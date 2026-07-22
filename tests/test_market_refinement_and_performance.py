from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from rust_companion_plus.services.deal_notifications import (
    collect_deal_alerts,
    normalize_notification_settings,
)
from rust_companion_plus.services.resource_heatmaps import (
    ResourceHeatmapBundle,
)
from rust_companion_plus.services.shop_value import (
    score_shop_rows,
    sort_scored_rows,
)
from rust_companion_plus.services.starter_spot import (
    recommend_starter_spots,
)
from rust_companion_plus.ui.tabs.map_enhanced import (
    render_zoomed_view,
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
    item_is_blueprint: bool = False
    currency_is_blueprint: bool = False

    @property
    def shop_key(self) -> str:
        return f"{self.shop}|{self.grid}"


class ProgressionAwareDealTests(unittest.TestCase):
    def _market(
        self,
        item_name: str,
        currency_name: str,
        costs: list[int],
        *,
        quantity: int = 1,
    ):
        return [
            Offer(
                100,
                200,
                quantity,
                cost,
                8,
                f"Shop {index}",
                item_name,
                currency_name,
                grid=f"A{index + 1}",
            )
            for index, cost in enumerate(costs)
        ]

    def test_hunting_bow_for_sulfur_is_never_an_urgent_deal(self) -> None:
        scored, _ = score_shop_rows(
            self._market(
                "Hunting Bow",
                "Sulfur Ore",
                [50, 100, 110, 120],
            )
        )
        best = sort_scored_rows(scored, "Best value")[0]
        self.assertEqual("Shop 0", best.row.shop)
        self.assertEqual("FAIR", best.deal.label)
        self.assertFalse(best.deal.actionable)
        alerts, _state = collect_deal_alerts(
            scored,
            {},
            profile_key="server:28015",
        )
        self.assertEqual([], alerts)

    def test_wood_for_stone_is_price_compared_but_not_called_a_steal(self) -> None:
        scored, _ = score_shop_rows(
            self._market(
                "Wood",
                "Stones",
                [100, 500, 550, 600],
                quantity=1000,
            )
        )
        best = sort_scored_rows(scored, "Best value")[0]
        self.assertEqual("FAIR", best.deal.label)
        self.assertLessEqual(best.deal.score, 58)
        self.assertIn(
            "not treated as an urgent progression purchase",
            best.deal.reason,
        )

    def test_deep_discount_on_high_tier_item_is_actionable(self) -> None:
        scored, _ = score_shop_rows(
            self._market(
                "Assault Rifle",
                "Scrap",
                [100, 500, 550, 600],
            )
        )
        best = sort_scored_rows(scored, "Best value")[0]
        self.assertIn(best.deal.label, {"STEAL", "CAN'T MISS"})
        self.assertTrue(best.deal.actionable)
        alerts, _state = collect_deal_alerts(
            scored,
            {},
            profile_key="server:28015",
        )
        self.assertEqual(1, len(alerts))
        self.assertIn(alerts[0].label, {"STEAL", "CAN'T MISS"})

    def test_legacy_listing_error_setting_migrates_to_real_rating(self) -> None:
        settings = normalize_notification_settings(
            {"minimum_rating": "Steal or better"}
        )
        self.assertEqual(
            "Steal or better",
            settings["minimum_rating"],
        )


class StarterAndMapPerformanceTests(unittest.TestCase):
    def test_remote_resource_rich_island_is_not_recommended(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            size = 72

            water = Image.new("L", (size, size), 255)
            draw_water = ImageDraw.Draw(water)
            # Large mainland on the right and a small isolated island on the left.
            draw_water.rectangle((20, 6, 68, 68), fill=0)
            draw_water.rectangle((2, 2, 9, 9), fill=0)

            stone = Image.new("L", (size, size), 0)
            road = Image.new("L", (size, size), 0)
            metal = Image.new("L", (size, size), 0)
            # Make the island look superficially excellent so landmass filtering,
            # not weak resources, is what rejects it.
            ImageDraw.Draw(stone).rectangle((2, 2, 9, 9), fill=255)
            ImageDraw.Draw(road).rectangle((2, 2, 9, 9), fill=255)
            ImageDraw.Draw(metal).rectangle((2, 2, 9, 9), fill=255)
            # Practical mainland candidate.
            ImageDraw.Draw(stone).ellipse((34, 30, 50, 46), fill=240)
            ImageDraw.Draw(road).ellipse((32, 28, 52, 48), fill=230)
            ImageDraw.Draw(metal).ellipse((38, 32, 54, 48), fill=210)

            paths = {}
            for name, image in (
                ("Water", water),
                ("Stone", stone),
                ("Road Access", road),
                ("Metal", metal),
            ):
                path = root / f"{name}.png"
                image.save(path)
                paths[name] = [path]

            bundle = ResourceHeatmapBundle(
                source_root=root,
                raster_layers=paths,
                detected_world_size=4000,
            )
            spots = recommend_starter_spots(
                bundle,
                4000,
                limit=3,
                resolution=size,
            )
            self.assertTrue(spots)
            self.assertTrue(
                all(spot.x_fraction >= 0.20 for spot in spots),
                spots,
            )
            self.assertIn(
                "mainland",
                " ".join(spots[0].reasons).casefold(),
            )

    def test_interactive_zoom_resizes_directly_to_display_size(self) -> None:
        source = Image.new("RGBA", (1600, 1600), (1, 2, 3, 255))
        result = render_zoomed_view(
            source,
            6.0,
            (0.5, 0.5),
            (640, 480),
            interactive=True,
        )
        self.assertEqual((640, 480), result.size)


class PerformanceSourceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def test_common_best_value_legacy_contract_is_progression_aware(self) -> None:
        source = self.read(
            "tests/test_feature_hubs_and_retention.py"
        )
        self.assertIn(
            'self.assertEqual("FAIR", ordered[0].deal.label)',
            source,
        )
        self.assertIn(
            "self.assertFalse(ordered[0].deal.actionable)",
            source,
        )
        self.assertNotIn(
            'self.assertIn(ordered[0].deal.label, {"STEAL", "CAN\'T MISS", "GOOD VALUE"})',
            source,
        )

    def test_targeted_notifier_preserves_app_context_contract(self) -> None:
        app = self.read("rust_companion_plus/app.py")
        self.assertIn(
            "    def notify_data_changed(self) -> None:\n"
            "        if self.app is not None:\n"
            "            self.app.notify_data_changed()",
            app,
        )
        self.assertEqual(
            1,
            app.count("tab_names: tuple[str, ...] | None = None"),
        )

    def test_full_market_refresh_is_split_from_one_second_team_poll(self) -> None:
        app = self.read("rust_companion_plus/app.py")
        client = self.read(
            "rust_companion_plus/services/rustplus_client.py"
        )
        self.assertIn("RUSTPLUS_INTERVAL_MS = 5_000", app)
        self.assertIn("TEAM_INTERVAL_MS = 1_000", app)
        self.assertIn("def refresh_team_now", app)
        self.assertIn("notify_data_changed((\"Overview\", \"Team\"))", app)
        self.assertIn("def fetch_team", client)

    def test_map_uses_cached_throttled_interactive_rendering(self) -> None:
        source = self.read(
            "rust_companion_plus/ui/tabs/map_enhanced.py"
        )
        self.assertIn("_composite_cache_key", source)
        self.assertIn("INTERACTION_FRAME_MS = 16", source)
        self.assertIn("Image.Resampling.BILINEAR", source)
        self.assertIn("_schedule_quality_render", source)

    def test_unchanged_market_does_not_rebuild_hundreds_of_rows(self) -> None:
        source = self.read(
            "rust_companion_plus/ui/tabs/shops_enhanced.py"
        )
        self.assertIn(
            "Marketplace unchanged; cached ratings reused.",
            source,
        )

    def test_listing_error_category_is_removed_everywhere_relevant(self) -> None:
        for relative in (
            "rust_companion_plus/services/shop_value.py",
            "rust_companion_plus/services/deal_notifications.py",
            "rust_companion_plus/ui/tabs/shops_enhanced.py",
            "rust_companion_plus/services/guide_catalog.py",
            "docs/FEATURE_GUIDE.md",
        ):
            self.assertNotIn(
                "POSSIBLE LISTING ERROR",
                self.read(relative),
                relative,
            )


if __name__ == "__main__":
    unittest.main()
