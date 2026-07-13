from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rust_companion_plus.services.server_finder import RustServerFinder, ServerCandidate


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


if __name__ == "__main__":
    unittest.main()
