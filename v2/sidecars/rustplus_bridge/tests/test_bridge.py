from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from v2.sidecars.rustplus_bridge.bridge import dispatch, redact
class BridgeTests(unittest.TestCase):
    def test_health_requires_no_credentials(self): self.assertTrue(dispatch({"command":"health"})["ok"])
    def test_secrets_are_redacted_recursively(self):
        value = redact({"player_token": 123, "nested": {"api_key": "x", "safe": 4}})
        self.assertEqual("***", value["player_token"]); self.assertEqual("***", value["nested"]["api_key"]); self.assertEqual(4, value["nested"]["safe"])
    def test_incomplete_credentials_fail_without_network(self): self.assertFalse(dispatch({"command":"snapshot","credentials":{}})["ok"])
if __name__ == "__main__": unittest.main()
