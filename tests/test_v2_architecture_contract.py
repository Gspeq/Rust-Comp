from __future__ import annotations
import json, re, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
class V2ArchitectureContractTests(unittest.TestCase):
    def test_v2_is_additive_and_has_launchers(self):
        self.assertTrue((ROOT / "main.py").is_file())
        self.assertTrue((ROOT / "Run_Rust_Companion_Plus_Source.bat").is_file())
        self.assertFalse((ROOT / "Run_Rust_Companion_Plus_V2_Dev.bat").exists())
        self.assertTrue(
            (ROOT / "v2" / "Run_Rust_Companion_Plus_V2_Dev.bat").is_file()
        )
        self.assertTrue((ROOT / "v2" / "Cargo.toml").is_file())
    def test_database_prepares_friend_and_shared_state(self):
        schema = (ROOT / "v2" / "migrations" / "0001_initial.sql").read_text(encoding="utf-8").casefold()
        for table in ("friendships", "blocked_users", "team_memberships", "objectives", "tactical_markers", "shopping_requests", "alarm_acknowledgements", "event_log"):
            self.assertIn(f"create table if not exists {table}", schema)
    def test_provider_catalog_covers_free_integrations(self):
        source = (ROOT / "v2" / "crates" / "integrations" / "src" / "lib.rs").read_text(encoding="utf-8")
        for provider in ("rustplus", "steam_openid", "discord", "battlemetrics", "rustmaps", "ntfy", "telegram", "matrix", "maxmind_geolite2", "opentelemetry", "web_push"):
            self.assertRegex(
                source,
                rf'provider\s*\(\s*"{re.escape(provider)}"',
            )
    def test_environment_example_contains_no_assigned_secrets(self):
        for line in (ROOT / "v2" / ".env.example").read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or line.startswith("DATABASE_URL=") or line.startswith("RUST_COMPANION_V2_BIND="): continue
            self.assertTrue(line.endswith("="), line)
    def test_frontend_package_is_valid_json(self):
        payload = json.loads((ROOT / "v2" / "apps" / "desktop" / "package.json").read_text(encoding="utf-8"))
        self.assertIn("test", payload["scripts"]); self.assertIn("build", payload["scripts"])
if __name__ == "__main__": unittest.main()
