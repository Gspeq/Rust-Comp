from __future__ import annotations

import inspect
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from rust_companion_plus import app
from rust_companion_plus import hotfix_map_interaction_v4 as v4
from rust_companion_plus import hotfix_map_shop as legacy
from rust_companion_plus.services.resource_heatmaps import (
    HeatPoint,
    ResourceHeatmapBundle,
)
from rust_companion_plus.ui.tabs import map_enhanced


class _Widget:
    def __init__(self, root_x: int, root_y: int):
        self.root_x = root_x
        self.root_y = root_y

    def winfo_rootx(self) -> int:
        return self.root_x

    def winfo_rooty(self) -> int:
        return self.root_y


class MapEventCoordinateTests(unittest.TestCase):
    def test_child_label_event_is_converted_to_outer_map_coordinates(self) -> None:
        target = _Widget(100, 200)
        child = _Widget(160, 270)
        event = SimpleNamespace(
            widget=child,
            x=40,
            y=50,
            x_root=200,
            y_root=320,
        )
        self.assertEqual(
            (100, 120),
            v4.event_coordinates_in_widget(event, target),
        )

    def test_coordinate_fallback_uses_event_widget_root(self) -> None:
        target = _Widget(100, 200)
        child = _Widget(160, 270)
        event = SimpleNamespace(widget=child, x=40, y=50)
        self.assertEqual(
            (100, 120),
            v4.event_coordinates_in_widget(event, target),
        )

    def test_click_release_opens_immediately_without_after_delay(self) -> None:
        instance = object.__new__(v4.ReliableInteractiveMapTab)
        instance.map_label = _Widget(100, 200)
        instance._reliable_press_origin = (100, 120)
        instance._reliable_dragged = False
        opened: list[tuple[int, int]] = []
        instance._open_marker_at = lambda x, y: opened.append((x, y))
        event = SimpleNamespace(
            widget=_Widget(160, 270),
            x=40,
            y=50,
            x_root=200,
            y_root=320,
        )
        with mock.patch.object(v4._OriginalMapTab, "_pan_end", return_value=None):
            v4.ReliableInteractiveMapTab._pan_end(instance, event)
        self.assertEqual([(100, 120)], opened)


class SafeWorkerTests(unittest.TestCase):
    def test_worker_result_is_delivered_by_main_thread_poll(self) -> None:
        callbacks = []
        results = []
        errors = []
        owner = SimpleNamespace(
            after=lambda _delay, callback: callbacks.append(callback)
        )
        v4.run_tk_worker(
            owner,
            lambda: 42,
            results.append,
            errors.append,
            poll_ms=10,
        )
        deadline = time.time() + 2.0
        while not results and not errors and time.time() < deadline:
            if callbacks:
                callbacks.pop(0)()
            else:
                time.sleep(0.01)
        self.assertEqual([42], results)
        self.assertEqual([], errors)


class StarterFallbackTests(unittest.TestCase):
    def test_relaxed_fallback_returns_ranked_buildable_spots(self) -> None:
        bundle = ResourceHeatmapBundle(source_root=Path("."))
        bundle.points = {
            "Stone": [HeatPoint("Stone", 0.50, 0.50, 2.0, "test")],
            "Metal": [HeatPoint("Metal", 0.53, 0.50, 2.0, "test")],
            "Road Access": [HeatPoint("Road Access", 0.48, 0.52, 2.0, "test")],
            "Temperate Biome": [HeatPoint("Temperate Biome", 0.50, 0.50, 1.5, "test")],
        }
        spots = v4.relaxed_starter_spots(bundle, 4000, limit=3)
        self.assertGreaterEqual(len(spots), 1)
        self.assertLessEqual(len(spots), 3)
        self.assertTrue(spots[0].grid)
        self.assertTrue(spots[0].reasons)
        self.assertIn("fallback ranking", " ".join(spots[0].cautions))

    def test_recommend_override_uses_safe_worker_helper(self) -> None:
        source = inspect.getsource(v4.ReliableInteractiveMapTab.recommend_starter_spot)
        self.assertIn("run_tk_worker", source)
        self.assertIn("relaxed_starter_spots", source)


class RuntimeWiringTests(unittest.TestCase):
    def test_live_app_and_map_module_use_v4_class(self) -> None:
        self.assertIs(map_enhanced.MapTab, v4.ReliableInteractiveMapTab)
        self.assertIs(app.MapTab, v4.ReliableInteractiveMapTab)
        self.assertIs(legacy.ClickableServerMarkerMapTab, v4.ReliableInteractiveMapTab)
        self.assertEqual(legacy.HOTFIX_ID, map_enhanced._map_layers_hotfix_installed)
        self.assertEqual(
            v4.HOTFIX_ID,
            map_enhanced._map_interaction_starter_hotfix_installed,
        )
        self.assertEqual(
            v4.HOTFIX_ID,
            app.RustCompanionApp._map_interaction_starter_hotfix_installed,
        )

    def test_v41_preserves_v3_error_and_drone_activation_contracts(self) -> None:
        from rust_companion_plus.ui.tabs import shops_enhanced

        self.assertEqual(
            legacy.HOTFIX_ID,
            app.RustCompanionApp._error_notification_hotfix_installed,
        )
        self.assertEqual(
            legacy.HOTFIX_ID,
            shops_enhanced._drone_filter_hotfix_installed,
        )

    def test_bootstrap_imports_v4_after_existing_hotfix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "rust_companion_plus" / "bootstrap.py").read_text(
            encoding="utf-8"
        )
        old_import = "import rust_companion_plus.hotfix_map_shop"
        new_import = "import rust_companion_plus.hotfix_map_interaction_v4"
        self.assertIn(old_import, text)
        self.assertIn(new_import, text)
        self.assertLess(text.index(old_import), text.index(new_import))


if __name__ == "__main__":
    unittest.main()
