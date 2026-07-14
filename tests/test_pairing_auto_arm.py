from __future__ import annotations

import inspect
import unittest

from rust_companion_plus import bootstrap


class PairingAutoArmTests(unittest.TestCase):
    def test_pairing_arms_automatically_without_input_race(self) -> None:
        rendered = inspect.getsource(bootstrap._listen_for_pairing)
        self.assertIn("PAIRING RECEIVER ARMED FOR A FRESH REQUEST", rendered)
        self.assertIn("No Enter key is required.", rendered)
        self.assertIn("drain_replayed", rendered)
        self.assertNotIn("input(", rendered)


if __name__ == "__main__":
    unittest.main()
