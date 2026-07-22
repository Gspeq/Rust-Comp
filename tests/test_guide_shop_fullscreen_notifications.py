from __future__ import annotations

import unittest
from pathlib import Path

from rust_companion_plus.services.guide_catalog import (
    GUIDE_SECTIONS,
    render_guide_markdown,
)
from rust_companion_plus.ui.tabs.shops_enhanced import (
    COMPACT_COLUMNS,
    COMPACT_COLUMN_WIDTHS,
)


EXPECTED_TABS = {
    "Overview",
    "Map",
    "Team",
    "Shops",
    "Electrical",
    "Smart Devices",
    "Saved Servers",
    "Notes",
}


class GuideAndNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_every_application_tab_has_a_guide_section(self) -> None:
        self.assertEqual(EXPECTED_TABS, set(GUIDE_SECTIONS))
        for section in GUIDE_SECTIONS.values():
            self.assertTrue(section.summary)
            self.assertTrue(section.useful_when)
            self.assertTrue(section.features)
            for feature in section.features:
                self.assertTrue(feature.description)
                self.assertTrue(feature.useful_when)

    def test_markdown_guide_matches_the_in_app_catalog(self) -> None:
        guide = (
            self.root
            / "docs"
            / "FEATURE_GUIDE.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(render_guide_markdown(), guide)

    def test_guide_button_is_global_and_navigation_header_is_gone(self) -> None:
        app = (
            self.root
            / "rust_companion_plus"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('text="NAVIGATION"', app)
        self.assertNotIn('"NAVIGATION"', app)
        self.assertIn("GuideWindow", app)
        self.assertIn('text="? Guide"', app)
        self.assertIn("self.guide_button.lift()", app)
        self.assertIn("def open_guide", app)


class CompactShopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_blueprint_filter_is_removed_but_bp_is_marked(self) -> None:
        source = (
            self.root
            / "rust_companion_plus"
            / "ui"
            / "tabs"
            / "shops_enhanced.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Blueprint mode", source)
        self.assertNotIn("BLUEPRINT_MODES", source)
        self.assertIn('f"BP: {row.item_name}"', source)
        self.assertIn('f"BP: {row.currency_name}"', source)
        self.assertIn('ctk.StringVar(value="Any offer")', source)

    def test_table_is_compact_and_omits_sideways_only_columns(self) -> None:
        self.assertEqual(
            (
                "shop",
                "grid",
                "sells",
                "quantity",
                "wants",
                "cost",
                "stock",
                "deal",
            ),
            COMPACT_COLUMNS,
        )
        self.assertNotIn("coordinates", COMPACT_COLUMNS)
        self.assertNotIn("type", COMPACT_COLUMNS)
        self.assertLessEqual(
            sum(COMPACT_COLUMN_WIDTHS.values()),
            900,
        )
        source = (
            self.root
            / "rust_companion_plus"
            / "ui"
            / "tabs"
            / "shops_enhanced.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_hide_horizontal_scrollbars", source)
        self.assertIn("grid_remove()", source)


class FullscreenNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_windows_native_notification_path_is_present(self) -> None:
        source = (
            self.root
            / "rust_companion_plus"
            / "ui"
            / "notifications.py"
        ).read_text(encoding="utf-8")
        self.assertIn("System.Windows.Forms.NotifyIcon", source)
        self.assertIn("ShowBalloonTip", source)
        self.assertIn("CREATE_NO_WINDOW", source)
        self.assertIn("Windows Notification Center", source)
        self.assertIn("show_windows_notification", source)

    def test_in_app_notification_remains_as_fallback(self) -> None:
        source = (
            self.root
            / "rust_companion_plus"
            / "ui"
            / "notifications.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ctk.CTkToplevel", source)
        self.assertIn("Open Shops", source)
        self.assertIn('window.attributes("-topmost", True)', source)


if __name__ == "__main__":
    unittest.main()
