from __future__ import annotations

import unittest

from rust_companion_plus.debug_tools import _credentials_summary, _redact


class _Credentials:
    host = "192.0.2.10"
    port = 28083
    steam_id = 76561199121283118
    player_token = 123456789

    @staticmethod
    def is_complete() -> bool:
        return True


class DebugToolsTests(unittest.TestCase):
    def test_redaction_hides_tokens_but_preserves_presence_flags(self) -> None:
        row = _redact(
            {
                "player_token": 123,
                "rustplus_auth_token": "secret",
                "player_token_present": True,
                "host": "192.0.2.10",
            }
        )
        self.assertEqual("<redacted>", row["player_token"])
        self.assertEqual("<redacted>", row["rustplus_auth_token"])
        self.assertTrue(row["player_token_present"])
        self.assertEqual("192.0.2.10", row["host"])

    def test_credentials_summary_never_contains_raw_player_token(self) -> None:
        summary = _credentials_summary(_Credentials())
        self.assertNotIn("player_token", summary)
        self.assertTrue(summary["player_token_present"])
        self.assertEqual("192.0.2.10", summary["host"])
        self.assertEqual("283118", summary["steam_suffix"])


if __name__ == "__main__":
    unittest.main()
