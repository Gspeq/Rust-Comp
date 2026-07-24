from __future__ import annotations

import json
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_ROOT = ROOT / "v2" / "apps" / "desktop" / "src-tauri"
PNG_SIGNATURE = bytes((137, 80, 78, 71, 13, 10, 26, 10))


class V2TauriResourceContractTests(unittest.TestCase):
    def test_configured_tauri_icons_exist(self) -> None:
        config = json.loads(
            (TAURI_ROOT / "tauri.conf.json").read_text(encoding="utf-8")
        )
        icons = config["bundle"]["icon"]
        self.assertGreaterEqual(len(icons), 4)
        for relative in icons:
            path = TAURI_ROOT / relative
            self.assertTrue(path.is_file(), path)
            self.assertGreater(path.stat().st_size, 16, path)

    def test_windows_icon_has_valid_multiframe_ico_header(self) -> None:
        payload = (TAURI_ROOT / "icons" / "icon.ico").read_bytes()
        self.assertGreaterEqual(len(payload), 22)
        reserved, kind, count = struct.unpack_from("<HHH", payload, 0)
        self.assertEqual(0, reserved)
        self.assertEqual(1, kind)
        self.assertGreaterEqual(count, 4)

    def test_png_icons_have_png_signatures(self) -> None:
        for name in ("32x32.png", "128x128.png", "128x128@2x.png"):
            payload = (TAURI_ROOT / "icons" / name).read_bytes()
            self.assertTrue(payload.startswith(PNG_SIGNATURE), name)


if __name__ == "__main__":
    unittest.main()
