from __future__ import annotations
import unittest
from rust_companion_plus.bootstrap import _apply_pairing_record
from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.pairing import PairingNotificationInbox, PairingRecord

class SplitPairingEndpointTests(unittest.TestCase):
    def test_inbox_returns_mismatched_complete_record(self) -> None:
        inbox = PairingNotificationInbox({"fcm_credentials": {"token": "unused"}})
        inbox._started = True
        inbox.records.put(PairingRecord(host="108.61.205.238", port=28083, steam_id=76561199121283118, player_token=987654321))
        record = inbox.wait_for("208.103.169.97", timeout=0.1)
        self.assertIsNotNone(record)
        self.assertEqual("108.61.205.238", record.host)

    def test_apply_uses_companion_host(self) -> None:
        current = RustCredentials(host="208.103.169.97")
        record = PairingRecord(host="108.61.205.238", port=28083, steam_id=76561199121283118, player_token=987654321)
        self.assertTrue(_apply_pairing_record(current, record, "208.103.169.97"))
        self.assertEqual("108.61.205.238", current.host)
        self.assertEqual(28083, current.port)

if __name__ == "__main__":
    unittest.main()
