from __future__ import annotations

import unittest
from pathlib import Path


class CleanRepositoryLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_only_two_root_batch_launchers_remain(self) -> None:
        expected = {
            "Run_Rust_Companion_Plus_Source.bat",
            "Build_Rust_Companion_Plus.bat",
        }
        actual = {path.name for path in self.root.glob("*.bat")}
        self.assertEqual(expected, actual)

    def test_source_launcher_runs_tests_before_main(self) -> None:
        runner = (
            self.root / "tools" / "windows" / "run_source.ps1"
        ).read_text(encoding="utf-8")
        lowered = runner.casefold()
        test_position = lowered.index('"unittest", "discover"')
        launch_position = lowered.index('(join-path $repo "main.py")')
        self.assertLess(test_position, launch_position)
        self.assertIn("origin/$branch", lowered)
        self.assertIn("git diff --check", lowered)
        self.assertNotIn("pyinstaller", lowered)
        self.assertNotIn("build_windows_release", lowered)

    def test_manual_builder_is_separate(self) -> None:
        source_launcher = (
            self.root / "Run_Rust_Companion_Plus_Source.bat"
        ).read_text(encoding="utf-8")
        build_launcher = (
            self.root / "Build_Rust_Companion_Plus.bat"
        ).read_text(encoding="utf-8")
        self.assertIn(
            r"tools\windows\run_source.ps1",
            source_launcher,
        )
        self.assertIn(
            r"tools\windows\build_windows_release.ps1",
            build_launcher,
        )
        self.assertNotIn("build_windows_release", source_launcher)

    def test_support_files_are_organized(self) -> None:
        required = (
            "docs/LAUNCHERS.md",
            "docs/WINDOWS_RELEASE.md",
            "requirements/build.txt",
            "requirements/core.txt",
            "tools/windows/run_source.ps1",
            "tools/windows/build_windows_release.ps1",
        )
        for relative in required:
            self.assertTrue((self.root / relative).is_file(), relative)

        forbidden = (
            "Test_Rust_Companion_Plus.bat",
            "test_source.ps1",
            "run_source.ps1",
            "build_windows_release.ps1",
            "LAUNCHERS.md",
            "WINDOWS_RELEASE.md",
            "requirements-build.txt",
            "requirements-core.txt",
            "RustCompanionPlus.spec",
        )
        for relative in forbidden:
            self.assertFalse((self.root / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
