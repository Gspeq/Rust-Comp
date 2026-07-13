from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rust_companion_plus.services.server_finder import (
    RustProcessSession,
    RustServerFinder,
    ServerCandidate,
    _parse_a2s_rules,
)


class ServerFinderTests(unittest.TestCase):
    def test_latest_raknet_line_after_disconnect_wins(self) -> None:
        text = (
            "2026-07-13T14:24:04.650Z|0x83f0|Connecting: 64.40.8.111:28010 (Raknet) "
            "2026-07-13T14:48:43.362Z|0x83f0|Disconnected (disconnect) - returning to main menu "
            "2026-07-13T14:48:48.059Z|0x83f0|Connecting: 64.40.8.112:28010 (Raknet) "
            "2026-07-13T14:48:52.415Z|0x83f0|Loading custom map from "
            "https://maps.rustmaps.com/286/example/wb3250_example.map"
        )
        finder = RustServerFinder()
        candidates, debug = finder._parse_log_text(text, Path("output_log.txt"))
        self.assertEqual(1, len(candidates), debug)
        self.assertEqual("64.40.8.112:28010", candidates[0].endpoint)
        self.assertEqual("rust_log_raknet", candidates[0].source)
        self.assertIn("rustmaps.com", candidates[0].metadata["map_url"])

    def test_connection_before_latest_disconnect_is_stale(self) -> None:
        text = (
            "2026-07-13T14:24:04.650Z|0x83f0|Connecting: 64.40.8.112:28010 (Raknet)\n"
            "2026-07-13T14:48:43.362Z|0x83f0|Disconnected (disconnect) - returning to main menu\n"
        )
        finder = RustServerFinder()
        candidates, debug = finder._parse_log_text(text, Path("output_log.txt"))
        self.assertEqual([], candidates)
        self.assertTrue(any("stale" in line for line in debug))

    def test_loopback_is_rejected(self) -> None:
        finder = RustServerFinder()
        candidate = ServerCandidate(
            host="127.0.0.1",
            port=32225,
            source="rust_process_remote_socket",
            confidence=0.76,
        )
        self.assertIn("loopback", finder._rejection_reason(candidate))

    def test_detect_once_prefers_log_over_socket_fallback(self) -> None:
        class TestFinder(RustServerFinder):
            def discover_log_paths(self):
                return [log_path]

            def _scan_rust_process_connections(self):
                return (
                    [
                        ServerCandidate(
                            host="168.100.161.166",
                            port=28015,
                            source="rust_process_remote_socket",
                            confidence=0.76,
                        )
                    ],
                    ["synthetic process candidate"],
                )

        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "output_log.txt"
            log_path.write_text(
                "2026-07-13T14:48:48.059Z|0x83f0|Connecting: 64.40.8.112:28010 (Raknet)\n",
                encoding="utf-8",
            )
            report = TestFinder().detect_once(enrich=False)
            self.assertIsNotNone(report.selected)
            self.assertEqual("64.40.8.112:28010", report.selected.endpoint)
            self.assertEqual("rust_log_raknet", report.selected.source)


    def test_running_process_is_required_for_launcher_detection(self) -> None:
        class ClosedRustFinder(RustServerFinder):
            def discover_log_paths(self):
                return [log_path]

            def get_rust_process_session(self):
                return RustProcessSession(
                    running=False,
                    debug=["synthetic: Rust is closed"],
                )

            def _scan_rust_process_connections(self):
                return [], ["synthetic: no sockets"]

        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "output_log.txt"
            log_path.write_text(
                "2026-07-13T14:48:48.059Z|0x83f0|Connecting: 64.40.8.112:28010 (Raknet)\n",
                encoding="utf-8",
            )
            report = ClosedRustFinder().detect_once(
                enrich=False,
                require_running_process=True,
                current_session_only=True,
            )
            self.assertIsNone(report.selected)
            self.assertTrue(any("not running" in line or "Rust is closed" in line for line in report.debug))

    def test_previous_process_session_log_is_rejected(self) -> None:
        text = (
            "2026-07-13T14:48:48.059Z|0x83f0|Connecting: 64.40.8.112:28010 (Raknet)\n"
        )
        finder = RustServerFinder()
        # Current Rust session starts well after the saved connection line.
        candidates, debug = finder._parse_log_text(
            text,
            Path("output_log.txt"),
            not_before_epoch=1783956000.0,
        )
        self.assertEqual([], candidates)
        self.assertTrue(any("previous-session" in line or "current-session" in line for line in debug))

    def test_current_process_session_log_is_accepted(self) -> None:
        text = (
            "2026-07-13T14:48:48.059Z|0x83f0|Connecting: 64.40.8.112:28010 (Raknet)\n"
        )
        finder = RustServerFinder()
        connection_epoch = 1783954128.059
        candidates, debug = finder._parse_log_text(
            text,
            Path("output_log.txt"),
            not_before_epoch=connection_epoch - 30.0,
        )
        self.assertEqual(1, len(candidates), debug)
        self.assertEqual("64.40.8.112:28010", candidates[0].endpoint)


    def test_current_log_can_publish_rust_app_port(self) -> None:
        text = (
            "2026-07-13T14:48:48.059Z|0x83f0|Connecting: 64.40.8.112:28010 (Raknet)\n"
            "2026-07-13T14:48:49.000Z|0x83f0|rust_app_port = 28082\n"
        )
        finder = RustServerFinder()
        candidates, debug = finder._parse_log_text(
            text,
            Path("output_log.txt"),
            not_before_epoch=1783954100.0,
        )
        self.assertEqual(1, len(candidates), debug)
        self.assertEqual(28082, candidates[0].metadata.get("rust_app_port"))

    def test_a2s_rules_parser_extracts_app_port(self) -> None:
        pairs = [
            (b"hostname", b"WarBandits"),
            (b"rust_app_port", b"28082"),
        ]
        payload = b"\xff\xff\xff\xffE" + len(pairs).to_bytes(2, "little")
        for key, value in pairs:
            payload += key + b"\x00" + value + b"\x00"
        rules = _parse_a2s_rules(payload)
        self.assertEqual("28082", rules["rust_app_port"])

    def test_log_port_beats_battlemetrics_port(self) -> None:
        finder = RustServerFinder()
        selected = ServerCandidate(
            host="64.40.8.112",
            port=28010,
            source="rust_log_raknet",
            confidence=0.99,
            metadata={"rust_app_port": 28082, "rust_app_port_source": "rust_log"},
        )
        from rust_companion_plus.services.server_finder import DetectionReport
        report = DetectionReport(
            scanned_at="now",
            selected=selected,
            battlemetrics={"rust_app_port": 29999},
        )
        finder._resolve_rust_app_port(report)
        self.assertEqual(28082, report.rust_app_port)
        self.assertEqual("rust_log", report.rust_app_port_source)


if __name__ == "__main__":
    unittest.main()
