from __future__ import annotations

import base64
import hashlib
import json
import socket
import threading
import unittest
from unittest.mock import patch

from rust_companion_plus import bootstrap, debug_tools
from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services import fcm_registration, server_finder
from rust_companion_plus.services.pairing import (
    PairingNotificationInbox,
    PairingRecord,
    _coerce_data_message_mapping,
    parse_pairing_payload,
)


class _AppDataMessage:
    def __init__(self, app_data) -> None:
        self.app_data = app_data


class _Selected:
    host = "203.0.113.10"
    port = 28015


class _Report:
    selected = _Selected()
    rust_app_port = 28082
    rust_app_port_source = (
        "facepunch_default_plus_67_websocket_probe"
    )
    battlemetrics = {}


class _Store:
    def __init__(self, values=None) -> None:
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value) -> None:
        self.values[key] = value


class RustPlusPreflightHardeningTests(unittest.TestCase):
    def test_specific_aliases_beat_generic_wrapper_fields(self) -> None:
        record = parse_pairing_payload(
            {
                "ip": "203.0.113.10",
                "port": 28015,
                "appPort": 28082,
                "playerId": 76561199121283118,
                "token": 111,
                "playerToken": 4294967295,
                "name": "Alias Test",
            }
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(28082, record.port)
        self.assertEqual(-1, record.player_token)

    def test_app_data_dictionary_is_normalized(self) -> None:
        mapping = _coerce_data_message_mapping(
            _AppDataMessage(
                {
                    "body": json.dumps(
                        {
                            "ip": "203.0.113.10",
                            "port": 28082,
                            "playerId": 76561199121283118,
                            "playerToken": -123,
                        }
                    )
                }
            )
        )
        record = parse_pairing_payload(mapping)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertTrue(record.is_complete())
        self.assertEqual(-123, record.player_token)

    def test_delayed_conflicting_authorization_is_ignored(self) -> None:
        inbox = PairingNotificationInbox(
            {"fcm_credentials": {"token": "unused"}}
        )
        inbox._started = True
        inbox.records.put(
            PairingRecord(
                host="203.0.113.10",
                port=28082,
                steam_id=76561199121283118,
                server_name="Fresh Server",
            )
        )
        inbox.records.put(
            PairingRecord(
                host="198.51.100.20",
                port=28084,
                steam_id=76561199121283118,
                player_token=123,
                server_name="Old Server",
            )
        )
        inbox.records.put(
            PairingRecord(
                host="203.0.113.10",
                port=28082,
                steam_id=76561199121283118,
                player_token=-456,
                server_name="Fresh Server",
            )
        )
        result = inbox.wait_for("203.0.113.10", timeout=0.5)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("203.0.113.10", result.host)
        self.assertEqual(-456, result.player_token)

    def test_saved_port_survives_heuristic_default_probe(self) -> None:
        store = _Store(
            {
                "credential_profiles": {
                    "203.0.113.10:28015": {
                        "host": "203.0.113.10",
                        "port": 28123,
                        "steam_id": 76561199121283118,
                        "player_token": -123,
                    }
                }
            }
        )
        _key, current = bootstrap._load_current_profile(store, _Report())
        self.assertEqual(28123, current.port)

    def test_websocket_probe_rejects_bad_accept_key(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def server() -> None:
            connection, _ = listener.accept()
            with connection:
                connection.recv(4096)
                connection.sendall(
                    b"HTTP/1.1 101 Switching Protocols\r\n"
                    b"Upgrade: websocket\r\n"
                    b"Connection: Upgrade\r\n"
                    b"Sec-WebSocket-Accept: wrong\r\n\r\n"
                )
            listener.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        success, detail = server_finder._probe_rustplus_websocket(
            "127.0.0.1",
            port,
            timeout=1.0,
        )
        thread.join(timeout=1.0)
        self.assertFalse(success)
        self.assertIn("invalid Sec-WebSocket-Accept", detail)

    def test_websocket_probe_verifies_correct_accept_key(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def server() -> None:
            connection, _ = listener.accept()
            with connection:
                request = connection.recv(4096).decode(
                    "ascii",
                    errors="replace",
                )
                key = ""
                for line in request.splitlines():
                    if line.casefold().startswith("sec-websocket-key:"):
                        key = line.split(":", 1)[1].strip()
                        break
                accept = base64.b64encode(
                    hashlib.sha1(
                        (
                            key
                            + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                        ).encode("ascii")
                    ).digest()
                ).decode("ascii")
                response = (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                )
                connection.sendall(response.encode("ascii"))
            listener.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        success, detail = server_finder._probe_rustplus_websocket(
            "127.0.0.1",
            port,
            timeout=1.0,
        )
        thread.join(timeout=1.0)
        self.assertTrue(success, detail)
        self.assertIn("accept key verified", detail)

    def test_nonempty_invalid_json_is_not_accepted_as_empty(self) -> None:
        class _Response:
            status = 200

            def read(self):
                return b"registration failed"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        with patch("urllib.request.urlopen", return_value=_Response()):
            with self.assertRaises(
                fcm_registration.FCMRegistrationError
            ):
                fcm_registration._request_json(
                    "https://example.invalid",
                    b"{}",
                    allow_empty=True,
                )

    def test_token_sign_is_safe_but_visible_in_diagnostics(self) -> None:
        summary = debug_tools._credentials_summary(
            RustCredentials(
                host="203.0.113.10",
                port=28082,
                steam_id=76561199121283118,
                player_token=-987654321,
            )
        )
        redacted = debug_tools._redact(summary)
        rendered = json.dumps(redacted)
        self.assertIn('"player_token_sign": "negative"', rendered)
        self.assertNotIn("987654321", rendered)


if __name__ == "__main__":
    unittest.main()
