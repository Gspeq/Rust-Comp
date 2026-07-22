from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from rust_companion_plus.services.bootstrap_health import (
    collect_bootstrap_issues,
    has_fatal_bootstrap_issue,
)
from rust_companion_plus.services.deal_notifications import (
    LOOT_PRESETS,
    collect_deal_alerts,
    normalize_notification_settings,
)
from rust_companion_plus.services.electrical_advisor import (
    strategic_recommendations,
)
from rust_companion_plus.services.shop_grid_map import (
    render_selected_shop_grid,
    shop_grid_crop_box,
)
from rust_companion_plus.services.smart_automation import (
    evaluate_rules,
    normalize_rules,
    normalize_scenes,
    normalize_systems,
    scene_plan,
    system_summary,
)
from rust_companion_plus.ui.tabs.map_enhanced import (
    ZOOM_LEVELS,
    zoom_crop,
)


@dataclass
class Row:
    shop: str = "Test Shop"
    grid: str = "G6"
    x: float = 1000
    y: float = 3000
    item_id: int = 1
    item_name: str = "Rocket"
    currency_id: int = 2
    currency_name: str = "Scrap"
    quantity: int = 1
    cost: int = 100
    stock: int = 3
    item_is_blueprint: bool = False
    currency_is_blueprint: bool = False

    @property
    def shop_key(self) -> str:
        return f"{self.shop}|{self.grid}"


@dataclass
class Deal:
    label: str = "FAIR"
    score: int = 50
    confidence: str = "High"
    reason: str = "Watched item listing."


@dataclass
class Scored:
    row: Row
    deal: Deal


class SmartAutomationTests(unittest.TestCase):
    def test_system_scene_and_rule_normalization(self) -> None:
        systems = normalize_systems(
            [
                {
                    "name": "North Defense",
                    "critical": True,
                    "device_ids": [1, "2", 99],
                }
            ],
            [1, 2, 3],
        )
        self.assertEqual([1, 2], systems[0]["device_ids"])

        scenes = normalize_scenes(
            [
                {
                    "name": "Raid Mode",
                    "actions": [
                        {"entity_id": 1, "value": True},
                        {"entity_id": 2, "value": False},
                    ],
                }
            ],
            [1, 2],
        )
        self.assertEqual(2, len(scenes[0]["actions"]))

        rules = normalize_rules(
            [
                {
                    "name": "Ammo low",
                    "source_entity_id": 2,
                    "condition": "Capacity below",
                    "threshold": 25,
                    "action": "Run scene",
                    "scene_id": scenes[0]["id"],
                }
            ],
            [1, 2],
            [scenes[0]["id"]],
        )
        self.assertEqual("Run scene", rules[0]["action"])

    def test_scene_plan_skips_already_set_and_system_summary(self) -> None:
        scene = {
            "actions": [
                {"entity_id": 1, "value": True},
                {"entity_id": 2, "value": False},
            ]
        }
        statuses = {
            1: {"value": True},
            2: {"value": True, "capacity": 20},
        }
        plan = scene_plan(scene, statuses)
        self.assertTrue(plan[0]["already_set"])
        self.assertFalse(plan[1]["already_set"])
        summary = system_summary(
            {"device_ids": [1, 2]},
            statuses,
        )
        self.assertEqual(2, summary["online"])
        self.assertEqual(2, summary["on"])
        self.assertEqual(20, summary["minimum_capacity"])

    def test_rules_use_transitions_thresholds_and_cooldowns(self) -> None:
        rules = [
            {
                "id": "one",
                "name": "Alarm on",
                "source_entity_id": 1,
                "condition": "Value turns ON",
                "threshold": 0,
                "action": "Notify only",
                "scene_id": "",
                "cooldown_seconds": 60,
                "enabled": True,
                "last_triggered_at": "",
            }
        ]
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        triggered, updated = evaluate_rules(
            rules,
            {1: {"value": True}},
            {1: {"value": False}},
            now=now,
        )
        self.assertEqual(1, len(triggered))
        repeated, _ = evaluate_rules(
            updated,
            {1: {"value": True}},
            {1: {"value": False}},
            now=now,
        )
        self.assertEqual([], repeated)


class NotificationPresetTests(unittest.TestCase):
    def test_all_progression_presets_exist(self) -> None:
        self.assertEqual(
            (
                "All loot",
                "Basic loot",
                "Mid tier loot",
                "High tier loot",
                "Endgame loot",
                "Custom items only",
            ),
            LOOT_PRESETS,
        )

    def test_specific_item_can_alert_even_when_deal_is_fair(self) -> None:
        settings = normalize_notification_settings(
            {
                "loot_preset": "Custom items only",
                "specific_items": "rocket, m249",
                "specific_item_any_listing": True,
            }
        )
        alerts, _state = collect_deal_alerts(
            [Scored(Row(item_name="Rocket"), Deal())],
            {},
            profile_key="server:28015",
            settings=settings,
        )
        self.assertEqual(1, len(alerts))
        self.assertEqual("WATCHED ITEM", alerts[0].label)

    def test_preset_stock_cost_and_blueprint_filters_apply(self) -> None:
        settings = {
            "loot_preset": "Endgame loot",
            "specific_item_any_listing": True,
            "specific_items": "rocket",
            "minimum_stock": 2,
            "maximum_cost": 200,
            "include_blueprints": False,
        }
        rows = [
            Scored(Row(item_name="Rocket", stock=1), Deal()),
            Scored(Row(item_name="Rocket", stock=3, cost=500), Deal()),
            Scored(
                Row(
                    item_name="Rocket",
                    stock=3,
                    cost=100,
                    item_is_blueprint=True,
                ),
                Deal(),
            ),
            Scored(Row(item_name="Rocket", stock=3, cost=100), Deal()),
        ]
        alerts, _state = collect_deal_alerts(
            rows,
            {},
            profile_key="server:28015",
            settings=settings,
        )
        self.assertEqual(1, len(alerts))


class MapAndElectricalTests(unittest.TestCase):
    def test_map_zoom_levels_are_extended_and_bounded(self) -> None:
        self.assertEqual(
            ("Fit", "1.5x", "2x", "3x", "4x", "6x", "8x"),
            ZOOM_LEVELS,
        )
        image = Image.new("RGBA", (500, 400), (1, 2, 3, 255))
        self.assertEqual(image.size, zoom_crop(image, 8, (0, 1)).size)

    def test_shop_map_is_one_fixed_grid_with_one_marker(self) -> None:
        base = Image.new("RGBA", (1000, 1000), (20, 30, 40, 255))
        selected = Row()
        box = shop_grid_crop_box(base.size, selected.x, selected.y, 4000)
        self.assertLess(box[2] - box[0], 100)
        rendered = render_selected_shop_grid(
            base,
            selected,
            4000,
            output_size=(200, 200),
        )
        self.assertEqual((200, 200), rendered.size)
        center_colors = {
            rendered.getpixel((x, y))[:3]
            for x in range(88, 113)
            for y in range(88, 113)
        }
        self.assertIn((245, 158, 11), center_colors)

    def test_strategic_electrical_advice_catches_endgame_risks(self) -> None:
        nodes = [
            {
                "id": f"t{index}",
                "component": "Auto Turret",
                "quantity": 1,
                "state": "Placed",
                "zone": "Defense",
            }
            for index in range(4)
        ]
        catalog = {
            "Auto Turret": {"category": "load"},
        }
        advice = strategic_recommendations(nodes, [], catalog)
        joined = "\n".join(advice)
        self.assertIn("battery", joined.casefold())
        self.assertIn("smart switch", joined.casefold())
        self.assertIn("smart alarm", joined.casefold())


class BootstrapHealthTests(unittest.TestCase):
    def _valid_source_root(self, root: Path) -> None:
        (root / "rust_companion_plus").mkdir()
        for name in (
            "launcher.py",
            "main.py",
            "Run_Rust_Companion_Plus_Source.bat",
            "Build_Rust_Companion_Plus.bat",
        ):
            (root / name).write_text("ok", encoding="utf-8")
        (root / "requirements.txt").write_text(
            "customtkinter>=5.2.2\n",
            encoding="utf-8",
        )

    def test_valid_source_and_appdata_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._valid_source_root(root)
            issues = collect_bootstrap_issues(
                root,
                root / "data",
                python_version=(3, 11, 0),
            )
            self.assertFalse(has_fatal_bootstrap_issue(issues))

    def test_missing_source_and_old_python_are_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            issues = collect_bootstrap_issues(
                root,
                root / "data",
                python_version=(3, 10, 0),
            )
            codes = {row["code"] for row in issues}
            self.assertIn("python_too_old", codes)
            self.assertIn("missing_source_files", codes)
            self.assertTrue(has_fatal_bootstrap_issue(issues))


class SourceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def test_smart_devices_expose_systems_scenes_rules(self) -> None:
        source = self.read("rust_companion_plus/ui/tabs/smart_devices.py")
        for text in (
            '"Systems"',
            '"Scenes"',
            '"Rules & Activity"',
            "create_system",
            "run_selected_scene",
            "evaluate_rules",
        ):
            self.assertIn(text, source)

    def test_electrical_opens_directly_to_visual_designer(self) -> None:
        hub = self.read("rust_companion_plus/ui/tabs/electrical_hub.py")
        electrical = self.read("rust_companion_plus/ui/tabs/electrical.py")
        self.assertNotIn("Simple Planner", hub)
        self.assertNotIn("CTkTabview", hub)
        self.assertIn("strategic_recommendations", electrical)

    def test_death_poll_is_one_second_and_guide_is_dashboard_only(self) -> None:
        app = self.read("rust_companion_plus/app.py")
        dashboard = self.read("rust_companion_plus/ui/tabs/dashboard.py")
        self.assertIn("RUSTPLUS_INTERVAL_MS = 5_000", app)
        self.assertIn("TEAM_INTERVAL_MS = 1_000", app)
        self.assertIn("def refresh_team_now", app)
        self.assertNotIn("self.guide_button", app)
        self.assertIn('text="? Feature Guide"', dashboard)
        self.assertIn("open_feature_guide", dashboard)

    def test_shop_and_map_controls_use_new_contracts(self) -> None:
        shops = self.read("rust_companion_plus/ui/tabs/shops.py")
        rustplus = self.read(
            "rust_companion_plus/services/rustplus_client.py"
        )
        map_source = self.read("rust_companion_plus/ui/tabs/map_enhanced.py")
        self.assertIn("render_selected_shop_grid", shops)
        self.assertIn("clean_map_image", shops)
        self.assertIn("fetch_clean_map", shops)
        self.assertIn("def fetch_clean_map", rustplus)
        self.assertIn("add_icons=False", rustplus)
        self.assertIn("add_events=False", rustplus)
        self.assertIn("add_vending_machines=False", rustplus)
        self.assertIn("add_team_positions=False", rustplus)
        self.assertIn("Quick overlays", map_source)
        self.assertIn("_pan_move", map_source)
        self.assertIn('"8x"', map_source)

    def test_dashboard_has_progression_and_specific_item_settings(self) -> None:
        panel = self.read(
            "rust_companion_plus/ui/notification_settings_panel.py"
        )
        self.assertIn("Loot preset", panel)
        self.assertIn("Specific items", panel)
        self.assertIn("Windows / fullscreen", panel)
        self.assertIn("Maximum total cost", panel)

    def test_bootstrap_exposes_local_self_check(self) -> None:
        bootstrap = self.read("rust_companion_plus/bootstrap.py")
        self.assertIn("--bootstrap-self-check", bootstrap)
        self.assertIn("collect_bootstrap_issues", bootstrap)
        self.assertIn("has_fatal_bootstrap_issue", bootstrap)


if __name__ == "__main__":
    unittest.main()
