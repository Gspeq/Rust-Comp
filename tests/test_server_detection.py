from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rust_companion_plus.services.server_detection import (
    ServerCandidate,
    ServerDetector,
    candidates_from_log,
    parse_endpoint,
)


class EndpointParsingTests(unittest.TestCase):
    def test_parse_ipv4_and_hostname(self) -> None:
        self.assertEqual(parse_endpoint("client.connect 203.0.113.10:28015"), ("203.0.113.10", 28015))
        self.assertEqual(parse_endpoint("steam://connect/play.example.net:28016"), ("play.example.net", 28016))

    def test_log_detection_prefers_latest_connection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "Player.log"
            path.write_text(
                "Connecting to 198.51.100.10:28015\nnoise\nClient connected to 203.0.113.20:28017\n",
                encoding="utf-8",
            )
            candidates = candidates_from_log(path)
            self.assertEqual(candidates[-1].host, "203.0.113.20")
            self.assertGreater(candidates[-1].confidence, candidates[0].confidence)

    def test_process_candidate_wins(self) -> None:
        detector = ServerDetector(
            log_paths=[],
            steam_history_paths=[],
            process_provider=lambda: [
                ServerCandidate("203.0.113.4", 28015, "process", 95),
                ServerCandidate("203.0.113.5", 28015, "process", 70),
            ],
        )
        self.assertEqual(detector.detect().host, "203.0.113.4")


if __name__ == "__main__":
    unittest.main()
