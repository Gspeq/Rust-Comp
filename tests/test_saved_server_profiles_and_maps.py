
from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from rust_companion_plus import bootstrap
from rust_companion_plus.app import (
    RustCompanionApp,
    load_startup_state,
)
from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.server_profiles import (
    ServerProfileVault,
    default_parsed_map_dir,
    discover_current_map_url,
    discover_saved_parsed_map,
    parse_current_server_map,
)
from rust_companion_plus.storage import JsonStore
from rust_companion_plus.ui.tabs.map_tab import MapTab


class SavedServerProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.store = JsonStore(root / "store.json")
        self.asset_root = root / "profiles"
        self.key = "45.88.230.116:28015"
        self.credentials = RustCredentials(
            host="45.88.230.116",
            port=28082,
            steam_id=76561199121283118,
            player_token=-123456789,
        )
        self.store.set(
            "credential_profiles",
            {
                self.key: self.credentials.to_dict(),
            },
        )
        self.store.set("notes", "Server-specific raid notes")
        self.store.set(
            "threats",
            [{"name": "Roof camper", "grid": "G19"}],
        )
        self.snapshot = {
            "server": {
                "name": "RustSpain EU Trio",
                "map": "Procedural Map",
                "size": 3800,
                "players": 87,
                "max_players": 200,
            },
            "team": [
                {
                    "steam_id": self.credentials.steam_id,
                    "name": "Taylor",
                    "x": 1000,
                    "y": 1000,
                    "is_online": True,
                    "is_alive": True,
                }
            ],
            "markers": [
                {
                    "id": 1,
                    "type": 3,
                    "x": 1200,
                    "y": 900,
                    "name": "Shop",
                    "sell_orders": [],
                }
            ],
            "server_time": "12:34",
        }
        self.map_url = (
            "https://maps.rustmaps.com/286/example/"
            "RustSpain_3800_example.map"
        )
        self.detection = {
            "selected": {
                "endpoint": self.key,
                "host": "45.88.230.116",
                "port": 28015,
                "metadata": {
                    "map_url": self.map_url,
                },
            },
            "battlemetrics": {
                "name": "RustSpain EU Trio",
            },
            "log_path": "",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def save_profile(self):
        vault = ServerProfileVault(
            self.store,
            asset_root=self.asset_root,
        )
        image = Image.new("RGBA", (32, 32), (10, 20, 30, 255))
        return vault.save_runtime_profile(
            key=self.key,
            credentials=self.credentials,
            snapshot=self.snapshot,
            detection=self.detection,
            timeline=[
                {
                    "time": "2026-07-14T16:00:00-04:00",
                    "category": "RUST+",
                    "message": "Live data received.",
                    "level": "info",
                }
            ],
            map_image=image,
            live_updated_at="2026-07-14T20:00:00+00:00",
        )

    def test_profile_archive_excludes_player_token(self) -> None:
        record = self.save_profile()
        rendered = json.dumps(record)
        self.assertNotIn(str(self.credentials.player_token), rendered)
        self.assertEqual(self.key, record["credential_profile_key"])
        self.assertEqual("RustSpain EU Trio", record["name"])
        self.assertEqual(1, record["summary"]["team_members"])
        self.assertEqual(1, record["summary"]["markers"])
        self.assertEqual(
            "Server-specific raid notes",
            record["workspace"]["notes"],
        )

    def test_saved_profile_loads_snapshot_credentials_and_map(self) -> None:
        record = self.save_profile()
        state = load_startup_state(self.store, self.key)

        self.assertTrue(state.profile_mode)
        self.assertEqual(self.key, state.active_profile_key)
        self.assertEqual(
            self.credentials.player_token,
            state.credentials.player_token,
        )
        self.assertIsNotNone(state.snapshot)
        assert state.snapshot is not None
        self.assertEqual(
            "RustSpain EU Trio",
            state.snapshot.server["name"],
        )
        self.assertIsNotNone(state.map_image)
        self.assertEqual(
            record["assets"]["map_image_path"],
            state.profile_record["assets"]["map_image_path"],
        )
        self.assertEqual(
            "Server-specific raid notes",
            self.store.get("notes"),
        )
        self.assertEqual(
            "Roof camper",
            self.store.get("threats")[0]["name"],
        )

    def test_map_url_is_taken_from_selected_server_metadata(self) -> None:
        self.assertEqual(
            self.map_url,
            discover_current_map_url(self.detection, {}),
        )

    def test_existing_profile_parsed_map_is_reused(self) -> None:
        parsed = default_parsed_map_dir(
            self.key,
            root=self.asset_root,
        )
        parsed.mkdir(parents=True, exist_ok=True)
        (parsed / "map_resolved.json").write_text(
            "{}",
            encoding="utf-8",
        )
        record = {
            "assets": {
                "parsed_map_dir": str(parsed),
            }
        }

        found = discover_saved_parsed_map(
            self.key,
            record,
            3800,
            root=self.asset_root,
        )
        self.assertEqual(parsed, found)

        result = parse_current_server_map(
            key=self.key,
            detection=self.detection,
            profile_record=record,
            world_size=3800,
            root=self.asset_root,
        )
        self.assertFalse(result.created)
        self.assertEqual(parsed, result.source_dir)

    def test_bootloader_can_select_saved_profile(self) -> None:
        self.save_profile()
        with patch(
            "builtins.input",
            side_effect=["s", "1"],
        ):
            mode, key = bootstrap.choose_launch_mode(
                self.store
            )
        self.assertEqual("saved", mode)
        self.assertEqual(self.key, key)

    def test_map_ui_has_only_automatic_profile_actions(self) -> None:
        source = inspect.getsource(MapTab)
        self.assertIn("Load current map", source)
        self.assertIn("View saved parsed map", source)
        self.assertIn("Analyze current map", source)
        self.assertNotIn("askopenfilename", source)
        self.assertNotIn("askdirectory", source)
        self.assertNotIn("Import parsed folder", source)
        self.assertNotIn("Auto-detect cache", source)
        self.assertNotIn("MapParser.exe", source)

    def test_app_has_close_save_prompt_and_profile_mode(self) -> None:
        source = inspect.getsource(RustCompanionApp)
        self.assertIn("WM_DELETE_WINDOW", source)
        self.assertIn("_save_current_profile", source)
        self.assertIn("Saved Profile · Live Rust+", source)
        self.assertIn("Saved Profile · Cached", source)
        self.assertIn("self.refresh_rustplus_now", source)


if __name__ == "__main__":
    unittest.main()
