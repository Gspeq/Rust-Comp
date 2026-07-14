from __future__ import annotations
import hashlib
import base64

import inspect
import json
import socket
import threading
import unittest

from rust_companion_plus import debug_tools
from rust_companion_plus.services import server_finder
from rust_companion_plus.services.pairing import (
    _safe_payload_inventory,
    parse_pairing_payload,
)


class PayloadStringAndPortProbeTests(unittest.TestCase):
    def test_nested_json_strings_merge_into_complete_record(self) -> None:
        payload = {
            "body": json.dumps(
                {
                    "ip": "45.88.230.116",
                    "port": 28082,
                    "name": "RustSpain",
                    "playerId": 76561199121283118,
                }
            ),
            "message": json.dumps(
                {
                    "playerToken": 987654321,
                }
            ),
        }

        record = parse_pairing_payload(payload)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertTrue(record.is_complete())
        self.assertEqual("45.88.230.116", record.host)
        self.assertEqual(28082, record.port)
        self.assertEqual(987654321, record.player_token)

    def test_safe_inventory_never_writes_token_value(self) -> None:
        secret = "98765432123456789"
        rows = _safe_payload_inventory(
            {
                "message": json.dumps(
                    {
                        "playerToken": secret,
                        "ip": "203.0.113.10",
                    }
                )
            }
        )
        rendered = json.dumps(rows)

        self.assertIn("playerToken", rendered)
        self.assertIn("<present>", rendered)
        self.assertNotIn(secret, rendered)
        self.assertIn("203.0.113.10", rendered)

    def test_websocket_probe_accepts_real_upgrade(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def server() -> None:
            connection, _address = listener.accept()
            with connection:
                request = connection.recv(4096).decode(
                    "ascii",
                    errors="replace",
                )
                key = ""
                for line in request.splitlines():
                    if line.casefold().startswith(
                        "sec-websocket-key:"
                    ):
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
                connection.sendall(
                    (
                        "HTTP/1.1 101 Switching Protocols\r\n"
                        "Upgrade: websocket\r\n"
                        "Connection: Upgrade\r\n"
                        f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                    ).encode("ascii")
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

        self.assertTrue(success, detail)
        self.assertIn("accept key verified", detail)


    def test_finder_uses_only_official_plus_67_candidate(self) -> None:
        rendered = inspect.getsource(
            server_finder.RustServerFinder._resolve_rust_app_port
        )
        self.assertIn("selected.port) + 67", rendered)
        self.assertIn("_probe_rustplus_websocket", rendered)
        self.assertNotIn("range(", rendered)

    def test_review_report_includes_new_evidence(self) -> None:
        rendered = inspect.getsource(debug_tools.create_review_report)
        self.assertIn("SAFE PAIRING PAYLOAD STRUCTURE", rendered)
        self.assertIn("NETWORK DISCOVERY DECISION", rendered)
        self.assertIn("PAIRING-RELEVANT RUST LOG LINES", rendered)


if __name__ == "__main__":
    unittest.main()
