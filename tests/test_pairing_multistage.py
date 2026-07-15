from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from rust_companion_plus.services.pairing import (
    PairingNotificationInbox,
    PairingRecord,
    parse_pairing_payload,
)


class MultiStagePairingTests(unittest.TestCase):
    def test_parser_merges_fields_across_nested_mappings(self) -> None:
        record = parse_pairing_payload(
            {
                "body": {
                    "ip": "135.148.137.125",
                    "port": 28082,
                    "name": "LoneRust",
                },
                "message": {
                    "playerId": 76561199121283118,
                    "playerToken": 987654321,
                },
            }
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertTrue(record.is_complete())
        self.assertEqual("135.148.137.125", record.host)
        self.assertEqual(28082, record.port)
        self.assertEqual(987654321, record.player_token)

    def test_wait_for_merges_partial_then_authorized_push(self) -> None:
        inbox = PairingNotificationInbox(
            {"fcm_credentials": {"token": "unused"}}
        )
        inbox._started = True
        inbox.records.put(
            PairingRecord(
                host="135.148.137.125",
                port=28082,
                steam_id=76561199121283118,
                server_name="LoneRust",
            )
        )
        inbox.records.put(
            PairingRecord(
                host="135.148.137.125",
                port=28082,
                steam_id=76561199121283118,
                player_token=987654321,
                server_name="LoneRust",
            )
        )

        record = inbox.wait_for("", timeout=0.2)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertTrue(record.is_complete())
        self.assertEqual(987654321, record.player_token)

    def test_wait_for_allows_later_companion_endpoint(self) -> None:
        inbox = PairingNotificationInbox(
            {"fcm_credentials": {"token": "unused"}}
        )
        inbox._started = True
        inbox.records.put(
            PairingRecord(
                host="208.103.169.97",
                port=28010,
                steam_id=76561199121283118,
                server_name="Rustoria",
            )
        )
        inbox.records.put(
            PairingRecord(
                host="108.61.205.238",
                port=28084,
                steam_id=76561199121283118,
                player_token=987654321,
                server_name="Rustoria",
            )
        )

        record = inbox.wait_for("", timeout=0.2)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual("108.61.205.238", record.host)
        self.assertEqual(28084, record.port)



if __name__ == "__main__":
    unittest.main()
