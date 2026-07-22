from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rust_companion_plus.services.deal_notifications import (
    collect_deal_alerts,
    normalize_notification_settings,
)
from rust_companion_plus.services.shop_value import (
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
    grid: str = "A1"
    item_name: str = "Assault Rifle"
    currency_name: str = "Scrap"
    item_is_blueprint: bool = False
    currency_is_blueprint: bool = False

    @property
    def shop_key(self) -> str:
        return f"{self.shop}|{self.grid}"


class DealAlgorithmTests(unittest.TestCase):
    def test_deep_robust_outlier_is_high_tier_urgent_deal(self) -> None:
        rows = [
            Offer(1, 2, 100, 10, 20, "Error"),
            Offer(1, 2, 100, 100, 20, "Normal A"),
            Offer(1, 2, 100, 105, 20, "Normal B"),
            Offer(1, 2, 100, 110, 20, "Normal C"),
        ]
        scored, _history = score_shop_rows(rows)
        ordered = sort_scored_rows(
            scored,
            "Best value",
        )
        self.assertEqual(
            "Error",
            ordered[0].row.shop,
        )
        self.assertEqual(
            "CAN'T MISS",
            ordered[0].deal.label,
        )
        self.assertGreaterEqual(
            ordered[0].deal.anomaly_score,
            2.5,
        )
        self.assertIn(
            "price rank",
            ordered[0].deal.reason,
        )

    def test_alerts_are_deduplicated(self) -> None:
        rows = [
            Offer(1, 2, 100, 10, 20, "Error"),
            Offer(1, 2, 100, 100, 20, "Normal A"),
            Offer(1, 2, 100, 105, 20, "Normal B"),
            Offer(1, 2, 100, 110, 20, "Normal C"),
        ]
        scored, _history = score_shop_rows(rows)
        when = datetime(
            2026,
            7,
            22,
            tzinfo=timezone.utc,
        )
        alerts, state = collect_deal_alerts(
            scored,
            {},
            profile_key="server:28015",
            now=when,
        )
        repeated, _state = collect_deal_alerts(
            scored,
            state,
            profile_key="server:28015",
            now=when,
        )
        self.assertEqual(1, len(alerts))
        self.assertEqual(
            "CAN'T MISS",
            alerts[0].label,
        )
        self.assertEqual([], repeated)



    def test_notification_settings_filter_and_bound_values(self) -> None:
        settings = normalize_notification_settings(
            {
                "enabled": True,
                "minimum_rating": "Can't miss only",
                "sound": False,
                "popup_seconds": 999,
                "repeat_hours": 0,
                "max_alerts": 50,
            }
        )
        self.assertEqual("Can't miss only", settings["minimum_rating"])
        self.assertFalse(settings["sound"])
        self.assertEqual(60, settings["popup_seconds"])
        self.assertEqual(1, settings["repeat_hours"])
        self.assertEqual(10, settings["max_alerts"])

class MarketplaceUiCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(
            __file__
        ).resolve().parents[1]

    def test_utilities_and_duplicate_navigation_removed(
        self,
    ) -> None:
        app = (
            self.root
            / "rust_companion_plus"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("ToolsTab", app)
        self.assertNotIn('"Utilities":', app)
        self.assertEqual(
            0,
            app.count('text="NAVIGATION"'),
        )

    def test_automatic_rustplus_failure_is_not_modal(
        self,
    ) -> None:
        app = (
            self.root
            / "rust_companion_plus"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"● Rust+ Reconnecting"',
            app,
        )
        self.assertNotIn(
            "first_new_error",
            app,
        )
        self.assertNotIn(
            'messagebox.showwarning(\n'
            '                    "Rust+ reconnecting"',
            app,
        )

    def test_marketplace_uses_text_ratings(
        self,
    ) -> None:
        shop = (
            self.root
            / "rust_companion_plus"
            / "ui"
            / "tabs"
            / "shops_enhanced.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"deal": "Deal rating"',
            shop,
        )
        self.assertIn(
            "collect_deal_alerts",
            shop,
        )
        self.assertIn("neutral", shop)
        for color in (
            "#14532d",
            "#166534",
            "#164e63",
            "#7f1d1d",
        ):
            self.assertNotIn(color, shop)

    def test_notification_center_is_application_code(
        self,
    ) -> None:
        app = (
            self.root
            / "rust_companion_plus"
            / "app.py"
        ).read_text(encoding="utf-8")
        center = (
            self.root
            / "rust_companion_plus"
            / "ui"
            / "notifications.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "DealNotificationCenter",
            app,
        )
        self.assertIn(
            "publish_deal_alerts",
            app,
        )
        self.assertIn(
            "class DealNotificationCenter",
            center,
        )
        self.assertIn(
            "Open Shops",
            center,
        )


    def test_dashboard_exposes_notification_setup(self) -> None:
        dashboard = (
            self.root / "rust_companion_plus" / "ui" / "tabs" / "dashboard.py"
        ).read_text(encoding="utf-8")
        panel = (
            self.root / "rust_companion_plus" / "ui" / "notification_settings_panel.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Marketplace Notifications", dashboard)
        self.assertIn("MarketplaceNotificationSettingsPanel", dashboard)
        self.assertIn("Save notification settings", panel)
        self.assertIn("Test notification", panel)
        self.assertIn("Clear alert history", panel)
        self.assertIn("Loot preset", panel)
        self.assertIn("Specific items", panel)
