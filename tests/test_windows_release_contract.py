from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

import rust_companion_plus.config as config
from rust_companion_plus import windows_app
from rust_companion_plus.windows_integration import find_uninstaller


class WindowsReleaseContractTests(unittest.TestCase):
    def test_application_data_is_outside_package(self) -> None:
        package = config.PACKAGE_DIR.resolve()
        application_data = config.APP_DATA_DIR.resolve()
        self.assertFalse(
            application_data == package
            or package in application_data.parents
        )
        self.assertEqual(
            config.APP_DATA_DIR / "logs",
            config.LOG_DIR,
        )

    def test_uninstaller_can_be_found_next_to_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = root / "unins000.exe"
            expected.write_bytes(b"MZ")
            self.assertEqual(
                expected,
                find_uninstaller(root),
            )

    def test_packaged_self_test_is_available(self) -> None:
        source = inspect.getsource(
            windows_app.packaged_self_test
        )
        self.assertIn("app_data_writable", source)
        self.assertIn("push_receiver", source)

    def test_release_files_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        required = (
            "build_windows_release.ps1",
            "Build_Rust_Companion_Plus.bat",
            "requirements-build.txt",
            "packaging/RustCompanionPlus.spec",
            "packaging/RustCompanionPlus.iss",
            "packaging/generate_windows_assets.py",
            "WINDOWS_RELEASE.md",
        )
        for relative in required:
            self.assertTrue(
                (root / relative).is_file(),
                relative,
            )

    def test_debug_launchers_are_removed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        forbidden = (
            "run_debug_windows.bat",
            "collect_debug_bundle.bat",
            "verify_dev_build.bat",
            "remove_dev_diagnostics.ps1",
            "rust_companion_plus/debug_tools.py",
            "tests/test_debug_tools.py",
        )
        for relative in forbidden:
            self.assertFalse(
                (root / relative).exists(),
                relative,
            )

    def test_installer_removes_application_data(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = (
            root / "packaging" / "RustCompanionPlus.iss"
        ).read_text(encoding="utf-8")
        self.assertIn("[UninstallDelete]", script)
        self.assertIn(
            r"{localappdata}\RustCompanionPlus\Rust Companion+",
            script,
        )
        self.assertIn("Uninstall Rust Companion+", script)

    def test_builder_uses_local_source_not_a_clone(self) -> None:
        root = Path(__file__).resolve().parents[1]
        builder = (
            root / "build_windows_release.ps1"
        ).read_text(encoding="utf-8")
        self.assertNotIn("git clone", builder.casefold())
        self.assertIn("requirements.txt", builder)
        self.assertIn("build-manifest.json", builder)

    def test_clean_release_declares_push_receiver(self) -> None:
        root = Path(__file__).resolve().parents[1]
        requirements = (root / "requirements.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "rustPlusPushReceiver==0.6.1",
            requirements,
        )

    def test_main_entry_uses_production_wrapper(self) -> None:
        root = Path(__file__).resolve().parents[1]
        main_source = (root / "main.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "rust_companion_plus.windows_app",
            main_source,
        )

    def test_app_contains_uninstall_action(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app_source = (
            root / "rust_companion_plus" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Uninstall Rust Companion+", app_source)
        self.assertIn("request_uninstall", app_source)


if __name__ == "__main__":
    unittest.main()
