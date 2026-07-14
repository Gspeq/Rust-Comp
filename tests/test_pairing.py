from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rust_companion_plus.services.pairing import PairingRecord, load_fcm_config, parse_pairing_payload


class PairingPayloadTests(unittest.TestCase):
    def test_nested_notification_is_parsed(self) -> None:
        payload = {
            "notification": {"title": "Pairing"},
            "data": {
                "ip": "64.40.8.112",
                "port": "28082",
                "playerId": "76561199121283118",
                "playerToken": "123456789",
                "name": "WarBandits",
            },
        }
        record = parse_pairing_payload(payload)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertTrue(record.is_complete())
        self.assertEqual("64.40.8.112", record.host)
        self.assertEqual(28082, record.port)
        self.assertEqual(76561199121283118, record.steam_id)
        self.assertEqual(123456789, record.player_token)

    def test_notification_body_json_string_is_parsed(self) -> None:
        payload = {
            "title": "Tap to pair",
            "body": json.dumps(
                {
                    "ip": "64.40.8.112",
                    "port": "28082",
                    "playerId": "76561199121283118",
                    "playerToken": "987654321",
                    "name": "WarBandits",
                }
            ),
        }
        record = parse_pairing_payload(payload)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertTrue(record.is_complete())
        self.assertEqual("64.40.8.112", record.host)
        self.assertEqual(28082, record.port)
        self.assertEqual(76561199121283118, record.steam_id)
        self.assertEqual(987654321, record.player_token)

    def test_pairing_json_file_is_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pairing.json"
            path.write_text(
                json.dumps(
                    {
                        "ip": "1.2.3.4",
                        "port": 12345,
                        "playerId": 76561198000000000,
                        "playerToken": 42,
                    }
                ),
                encoding="utf-8",
            )
            record = parse_pairing_payload(str(path))
            self.assertIsNotNone(record)
            assert record is not None
            self.assertTrue(record.matches_host("1.2.3.4"))
            self.assertIn("pairing_file", record.source)

    def test_incomplete_noise_is_not_complete(self) -> None:
        record = parse_pairing_payload({"name": "not a pairing"})
        self.assertIsNotNone(record)
        assert record is not None
        self.assertFalse(record.is_complete())

    def test_fcm_config_validation(self) -> None:
        valid = {"fcm_credentials": {"token": "x"}}
        self.assertEqual(valid, load_fcm_config(valid))
        self.assertIsNone(load_fcm_config({"other": {}}))


if __name__ == "__main__":
    unittest.main()
