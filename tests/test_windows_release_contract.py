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
        self.assertIn(
            r"{%USERPROFILE}\.rust_companion_plus",
            script,
        )
        self.assertNotIn(
            "{userprofile}",
            script.casefold(),
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

    def test_spec_resolves_repository_entrypoint(self) -> None:
        root = Path(__file__).resolve().parents[1]
        spec = (
            root / "packaging" / "RustCompanionPlus.spec"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "SPEC_DIR = Path(SPECPATH).resolve()",
            spec,
        )
        self.assertIn("ROOT = SPEC_DIR.parent", spec)
        self.assertNotIn("parent.parent", spec)
        self.assertIn(
            'ENTRYPOINT = ROOT / "main.py"',
            spec,
        )
        self.assertIn(
            "if not ENTRYPOINT.is_file()",
            spec,
        )
        self.assertIn("[str(ENTRYPOINT)]", spec)

    def test_builder_preflights_resolved_entrypoint(self) -> None:
        root = Path(__file__).resolve().parents[1]
        builder = (
            root / "build_windows_release.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '$Entrypoint = Join-Path $Repo "main.py"',
            builder,
        )
        self.assertIn(
            "PyInstaller entrypoint: $ResolvedEntrypoint",
            builder,
        )
        self.assertIn(
            "$EntrypointParent -ne $ResolvedRepo",
            builder,
        )

    def test_packaged_rustplus_transport_is_pinned(self) -> None:
        root = Path(__file__).resolve().parents[1]
        requirements = (root / "requirements.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("rustplus==6.0.11", requirements)
        self.assertIn("websockets==13.1", requirements)

        spec = (
            root / "packaging" / "RustCompanionPlus.spec"
        ).read_text(encoding="utf-8")
        self.assertIn("websockets.legacy.client", spec)
        self.assertIn("websockets.legacy.protocol", spec)

    def test_gui_hides_packaged_console_after_launch(self) -> None:
        root = Path(__file__).resolve().parents[1]
        integration = (
            root
            / "rust_companion_plus"
            / "windows_integration.py"
        ).read_text(encoding="utf-8")
        app = (
            root / "rust_companion_plus" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("GetConsoleWindow", integration)
        self.assertIn("ShowWindow", integration)
        self.assertIn(
            "self.after(350, hide_console_window)",
            app,
        )

    def test_gui_surfaces_rustplus_refresh_failure(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app = (
            root / "rust_companion_plus" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"Rust+ reconnecting"', app)
        self.assertIn("first_new_error", app)
    def test_source_runner_never_builds_release(self) -> None:
        root = Path(__file__).resolve().parents[1]
        runner = (root / "run_source.ps1").read_text(
            encoding="utf-8"
        )
        lowered = runner.casefold()
        self.assertIn(
            "rust_companion_hide_console_after_gui",
            lowered,
        )
        self.assertNotIn("pyinstaller", lowered)
        self.assertNotIn("inno setup", lowered)
        self.assertNotIn("build_windows_release", lowered)

    def test_test_runner_never_builds_release(self) -> None:
        root = Path(__file__).resolve().parents[1]
        runner = (root / "test_source.ps1").read_text(
            encoding="utf-8"
        )
        lowered = runner.casefold()
        self.assertIn("unittest discover", lowered)
        self.assertIn("git diff --check", lowered)
        self.assertNotIn("build_windows_release", lowered)

    def test_release_builder_remains_manual(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source_launcher = (
            root / "Run_Rust_Companion_Plus_Source.bat"
        ).read_text(encoding="utf-8")
        test_launcher = (
            root / "Test_Rust_Companion_Plus.bat"
        ).read_text(encoding="utf-8")
        build_launcher = (
            root / "Build_Rust_Companion_Plus.bat"
        ).read_text(encoding="utf-8")

        self.assertIn("run_source.ps1", source_launcher)
        self.assertIn("test_source.ps1", test_launcher)
        self.assertIn(
            "build_windows_release.ps1",
            build_launcher,
        )
        self.assertNotIn(
            "build_windows_release.ps1",
            source_launcher,
        )
        self.assertNotIn(
            "build_windows_release.ps1",
            test_launcher,
        )

if __name__ == "__main__":
    unittest.main()
