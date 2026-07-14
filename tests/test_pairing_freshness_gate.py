from __future__ import annotations

import inspect
import unittest

from rust_companion_plus import bootstrap
from rust_companion_plus.services.pairing import PairingNotificationInbox


class PairingFreshnessGateTests(unittest.TestCase):
    def test_launcher_waits_for_receiver_and_drains_until_quiet(self) -> None:
        rendered = inspect.getsource(bootstrap._listen_for_pairing)
        self.assertIn("wait_until_ready", rendered)
        self.assertIn("drain_replayed", rendered)
        self.assertIn("PAIRING RECEIVER ARMED FOR A FRESH REQUEST", rendered)
        self.assertIn("No Enter key is required.", rendered)
        self.assertNotIn("input(", rendered)
        self.assertNotIn("unpair and pair again", rendered.casefold())

    def test_inbox_exposes_quiet_window_drain(self) -> None:
        rendered = inspect.getsource(
            PairingNotificationInbox.drain_replayed
        )
        self.assertIn("quiet_deadline", rendered)
        self.assertIn("final_deadline", rendered)
        self.assertIn("pairing_stale_drain_completed", rendered)


if __name__ == "__main__":
    unittest.main()
