from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rust_companion_plus import app, bootstrap
from rust_companion_plus import hotfix_offline_saved_profiles_v5 as hotfix
from rust_companion_plus.ui.tabs import profiles


class OfflineLaunchCommandTests(unittest.TestCase):
    def test_source_command_keeps_profile_key_and_main_entrypoint(self) -> None:
        command = hotfix.build_saved_profile_launch_command(
            "203.0.113.10:28015",
            executable=r"C:\Python\python.exe",
            frozen=False,
            entrypoint=r"C:\Rust-Comp\main.py",
        )
        self.assertEqual(r"C:\Python\python.exe", command[0])
        self.assertEqual(str(Path(r"C:\Rust-Comp\main.py").resolve()), command[1])
        self.assertEqual(
            ["--saved-profile", "203.0.113.10:28015"],
            command[2:],
        )

    def test_frozen_command_reuses_application_executable(self) -> None:
        command = hotfix.build_saved_profile_launch_command(
            "203.0.113.11:28015",
            executable=r"C:\Apps\RustCompanionPlus.exe",
            frozen=True,
        )
        self.assertEqual(
            [
                r"C:\Apps\RustCompanionPlus.exe",
                "--saved-profile",
                "203.0.113.11:28015",
            ],
            command,
        )

    def test_blank_profile_key_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            hotfix.build_saved_profile_launch_command("  ")


class OfflineRuntimeWiringTests(unittest.TestCase):
    def test_app_and_profiles_modules_use_offline_classes(self) -> None:
        self.assertIs(app.RustCompanionApp, hotfix.OfflineFirstRustCompanionApp)
        self.assertIs(app.SavedServersTab, hotfix.OfflineSavedServersTab)
        self.assertIs(profiles.SavedServersTab, hotfix.OfflineSavedServersTab)

    def test_bootstrap_imports_v5_after_map_v4(self) -> None:
        source = inspect.getsource(bootstrap)
        self.assertIn("hotfix_offline_saved_profiles_v5", source)
        self.assertGreater(
            source.index("hotfix_offline_saved_profiles_v5"),
            source.index("hotfix_map_interaction_v4"),
        )
        self.assertIn(
            "Open saved server offline (Rust can be closed)",
            source,
        )
        self.assertIn(
            "automatic Rust+ polling stays off until Try live",
            source,
        )

    def test_cached_profile_blocks_automatic_rustplus_refresh(self) -> None:
        instance = object.__new__(hotfix.OfflineFirstRustCompanionApp)
        instance.context = SimpleNamespace(profile_mode=True)
        instance._saved_profile_live_refresh_enabled = False
        with patch.object(
            hotfix._BaseRustCompanionApp,
            "refresh_rustplus_now",
        ) as base_refresh:
            instance.refresh_rustplus_now()
        base_refresh.assert_not_called()

    def test_cached_profile_blocks_automatic_team_refresh(self) -> None:
        instance = object.__new__(hotfix.OfflineFirstRustCompanionApp)
        instance.context = SimpleNamespace(profile_mode=True)
        instance._saved_profile_live_refresh_enabled = False
        with patch.object(
            hotfix._BaseRustCompanionApp,
            "refresh_team_now",
        ) as base_refresh:
            instance.refresh_team_now()
        base_refresh.assert_not_called()

    def test_manual_enable_allows_base_refresh(self) -> None:
        instance = object.__new__(hotfix.OfflineFirstRustCompanionApp)
        instance.context = SimpleNamespace(profile_mode=True)
        instance._saved_profile_live_refresh_enabled = True
        with patch.object(
            hotfix._BaseRustCompanionApp,
            "refresh_rustplus_now",
        ) as base_refresh:
            instance.refresh_rustplus_now()
        base_refresh.assert_called_once_with()

    def test_replacement_class_preserves_legacy_source_contract(self) -> None:
        source = inspect.getsource(app.RustCompanionApp)
        for marker in (
            "WM_DELETE_WINDOW",
            "_save_current_profile",
            "Saved Profile · Live Rust+",
            "Saved Profile · Cached",
            "self.refresh_rustplus_now",
        ):
            self.assertIn(marker, source)


class SavedServersTabContractTests(unittest.TestCase):
    def test_ui_exposes_button_and_double_click(self) -> None:
        source = inspect.getsource(hotfix.OfflineSavedServersTab)
        self.assertIn("Open selected offline", source)
        self.assertIn('self.tree.bind("<Double-1>"', source)
        self.assertIn("Rust does not need to be running", source)

    def test_open_selected_launches_new_cached_process(self) -> None:
        fake = SimpleNamespace(
            context=SimpleNamespace(
                profile_mode=False,
                active_profile_key="",
            ),
            status=SimpleNamespace(configure=lambda **_kwargs: None),
            _selected_profile=lambda: {
                "key": "203.0.113.12:28015",
                "name": "Saved Test Server",
            },
        )
        with patch.object(hotfix, "launch_saved_profile_process") as launch:
            hotfix.OfflineSavedServersTab.open_selected_offline(fake)
        launch.assert_called_once_with("203.0.113.12:28015")


if __name__ == "__main__":
    unittest.main()
