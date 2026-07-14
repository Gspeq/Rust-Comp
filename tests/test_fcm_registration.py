from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rust_companion_plus.services.fcm_registration import (
    FCMRegistrationError,
    _RustPlusAuthBridge,
    _bridge_script,
    _extract_fcm_token,
    register_fcm_config,
)


class FCMRegistrationTests(unittest.TestCase):
    def test_extract_fcm_token(self) -> None:
        self.assertEqual("abc", _extract_fcm_token({"fcm": {"token": "abc"}}))
        with self.assertRaises(FCMRegistrationError):
            _extract_fcm_token({})

    def test_bridge_script_is_host_restricted(self) -> None:
        script = _bridge_script()
        self.assertIn("ReactNativeWebView", script)
        self.assertIn("window.pywebview.api.capture", script)
        self.assertIn("facepunch.com", script)
        self.assertNotIn("disable-web-security", script)

    def test_capture_only_records_token(self) -> None:
        bridge = _RustPlusAuthBridge()
        self.assertFalse(bridge.capture("not-json"))
        self.assertTrue(bridge.capture(json.dumps({"Token": "steam-token"})))
        self.assertEqual("steam-token", bridge.token)
        self.assertTrue(bridge.token_ready.is_set())
        self.assertFalse(hasattr(bridge, "window"))

    def test_registration_orchestration_saves_complete_config(self) -> None:
        events: list[str] = []
        registrations: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rustplus_fcm.json"
            config = register_fcm_config(
                output,
                status=events.append,
                android_register=lambda: {"fcm": {"token": "device-token"}},
                expo_token_fetcher=lambda token: f"expo:{token}",
                auth_token_fetcher=lambda _timeout: "steam-auth-token",
                push_registrar=lambda auth, expo: registrations.append((auth, expo)),
            )
            self.assertEqual([("steam-auth-token", "expo:device-token")], registrations)
            self.assertEqual(config, json.loads(output.read_text(encoding="utf-8")))
            self.assertEqual("device-token", config["fcm_credentials"]["fcm"]["token"])
            self.assertGreaterEqual(len(events), 4)


if __name__ == "__main__":
    unittest.main()
