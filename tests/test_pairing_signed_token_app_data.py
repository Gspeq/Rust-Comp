from __future__ import annotations

import json
import unittest

from rust_companion_plus.models import (
    RustCredentials,
    normalize_player_token,
)
from rust_companion_plus.services.pairing import (
    PairingNotificationInbox,
    PairingRecord,
    _coerce_data_message_mapping,
    parse_pairing_payload,
)


class _Entry:
    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value


class _Stanza:
    def __init__(self, entries: list[_Entry]) -> None:
        self.app_data = entries


class SignedTokenAndAppDataTests(unittest.TestCase):
    def test_signed_negative_token_is_complete(self) -> None:
        record = PairingRecord(
            host="45.88.230.116",
            port=28082,
            steam_id=76561199121283118,
            player_token=-123456789,
        )
        self.assertTrue(record.is_complete())

    def test_unsigned_int32_form_is_normalized(self) -> None:
        self.assertEqual(-1, normalize_player_token(4294967295))
        credentials = RustCredentials.from_dict(
            {
                "host": "203.0.113.5",
                "port": 28082,
                "steam_id": 76561199121283118,
                "player_token": 4294967295,
            }
        )
        self.assertEqual(-1, credentials.player_token)
        self.assertTrue(credentials.is_complete())

    def test_app_data_body_supplies_authoritative_token(self) -> None:
        body = json.dumps(
            {
                "type": "server",
                "ip": "45.88.230.116",
                "port": 28082,
                "playerId": 76561199121283118,
                "playerToken": -123456789,
                "name": "RustSpain",
            }
        )
        stanza = _Stanza(
            [
                _Entry("channelId", "pairing"),
                _Entry("body", body),
            ]
        )

        normalized = _coerce_data_message_mapping(stanza)
        record = parse_pairing_payload(normalized)

        self.assertEqual("pairing", normalized["channelId"])
        self.assertIsNotNone(record)
        assert record is not None
        self.assertTrue(record.is_complete())
        self.assertEqual(-123456789, record.player_token)

    def test_quiet_window_drain_discards_replays(self) -> None:
        inbox = PairingNotificationInbox(
            {"fcm_credentials": {"token": "unused"}}
        )
        inbox._started = True
        inbox.records.put(
            PairingRecord(
                host="198.51.100.10",
                port=28082,
                steam_id=76561199121283118,
                player_token=100,
                server_name="Old Server",
            )
        )

        discarded = inbox.drain_replayed(
            quiet_period=0.01,
            max_wait=0.10,
        )

        self.assertEqual(1, discarded)
        self.assertTrue(inbox.records.empty())


if __name__ == "__main__":
    unittest.main()
