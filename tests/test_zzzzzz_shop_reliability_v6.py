from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from tkinter import TclError
from types import SimpleNamespace

import rust_companion_plus.hotfix_map_shop as legacy
import rust_companion_plus.hotfix_shop_reliability_v6 as hotfix
from rust_companion_plus import app


class _RecordingInnerLabel:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def configure(self, **kwargs) -> None:
        self.calls.append(dict(kwargs))


class _RecordingLabel:
    def __init__(self, owner, *, fail_once: bool = False) -> None:
        self.owner = owner
        self.fail_once = fail_once
        self.calls: list[dict] = []
        self.reference_was_alive = False
        self._label = _RecordingInnerLabel()
        self._image = object()

    def configure(self, **kwargs) -> None:
        self.reference_was_alive = self.owner._minimap_ctk_image is not None
        self.calls.append(dict(kwargs))
        if self.fail_once:
            self.fail_once = False
            raise TclError('image "pyimage2" doesn\'t exist')


class MinimapImageLifetimeTests(unittest.TestCase):
    def test_widget_detaches_before_python_reference_is_released(self) -> None:
        owner = SimpleNamespace(_minimap_ctk_image=object())
        owner.minimap_label = _RecordingLabel(owner)

        changed = hotfix.detach_minimap_image_before_release(owner)

        self.assertTrue(changed)
        self.assertTrue(owner.minimap_label.reference_was_alive)
        self.assertEqual({"image": None}, owner.minimap_label.calls[0])
        self.assertIsNone(owner._minimap_ctk_image)

    def test_deleted_tk_image_recovers_through_inner_label(self) -> None:
        owner = SimpleNamespace(_minimap_ctk_image=object())
        owner.minimap_label = _RecordingLabel(owner, fail_once=True)

        changed = hotfix.detach_minimap_image_before_release(owner)

        self.assertTrue(changed)
        self.assertEqual({"image": ""}, owner.minimap_label._label.calls[0])
        self.assertIsNone(owner.minimap_label._image)
        self.assertIsNone(owner._minimap_ctk_image)


class DroneReachabilityRemovalTests(unittest.TestCase):
    def test_application_uses_reliable_marketplace_class(self) -> None:
        self.assertIs(app.ShopsTab, hotfix.ReliableMarketplaceShopsTab)
        self.assertEqual(
            hotfix.HOTFIX_ID,
            app.SHOP_RELIABILITY_HOTFIX_ID,
        )

    def test_active_class_does_not_inherit_drone_filter_ui(self) -> None:
        self.assertFalse(
            issubclass(
                hotfix.ReliableMarketplaceShopsTab,
                legacy.DroneMarketplaceShopsTab,
            )
        )
        source = inspect.getsource(hotfix.ReliableMarketplaceShopsTab)
        self.assertNotIn("Drone Marketplace shops only", source)
        self.assertNotIn("drone_marketplace_only", source)

    def test_notice_does_not_claim_reachability(self) -> None:
        notice = hotfix.DRONE_REACHABILITY_NOTICE.casefold()
        self.assertIn("does not expose walls", notice)
        self.assertIn("does not infer", notice)
        self.assertNotIn("drone accessible", notice)

    def test_bootstrap_activates_v6_after_saved_profile_hotfix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "rust_companion_plus" / "bootstrap.py"
        ).read_text(encoding="utf-8")
        v5 = "import rust_companion_plus.hotfix_offline_saved_profiles_v5"
        v6 = "import rust_companion_plus.hotfix_shop_reliability_v6"
        self.assertIn(v5, source)
        self.assertIn(v6, source)
        self.assertLess(source.index(v5), source.index(v6))


if __name__ == "__main__":
    unittest.main()
