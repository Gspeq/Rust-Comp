from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class V2RootLayoutRegressionTests(unittest.TestCase):
    def test_v2_launcher_does_not_expand_legacy_root_bat_set(self) -> None:
        self.assertFalse(
            (ROOT / "Run_Rust_Companion_Plus_V2_Dev.bat").exists(),
            "V2-specific launchers must stay under v2/ so the legacy root "
            "launcher allowlist remains unchanged.",
        )
        launcher = ROOT / "v2" / "Run_Rust_Companion_Plus_V2_Dev.bat"
        self.assertTrue(launcher.is_file())
        source = launcher.read_text(encoding="utf-8").casefold()
        self.assertIn("tools\\run_dev.ps1", source)


if __name__ == "__main__":
    unittest.main()
