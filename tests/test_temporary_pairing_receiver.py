from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rust_companion_plus import bootstrap
from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.fcm_registration import (
    cleanup_lingering_fcm_registration,
    refresh_fcm_registration,
    unregister_fcm_registration,
)
from rust_companion_plus.services.pairing import PairingRecord


class _Session:
    running = True


class _Finder:
    def get_rust_process_session(self):
        return _Session()


class _Inbox:
    instances = []

    def __init__(self, config):
        self.config = config
        self.drained = False
        self.__class__.instances.append(self)

    def start(self):
        return None

    def wait_until_ready(self, timeout=0):
        return True

    def drain_replayed(self, **_kwargs):
        self.drained = True
        return 0

    def wait_for(self, _host, **_kwargs):
        return PairingRecord(
            host="203.0.113.10",
            port=28082,
            steam_id=76561199121283118,
            player_token=-123,
            server_name="Temporary Receiver Test",
            source="test",
        )


class TemporaryPairingReceiverTests(unittest.TestCase):
    def config(self):
        return {
            "fcm_credentials": {"fcm": {"token": "device-token"}},
            "expo_push_token": "expo-token",
            "rustplus_auth_token": "auth-token",
            "device_id": "rustplus.py",
        }

    def test_refresh_marks_receiver_temporarily_active(self):
        calls = []
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fcm.json"
            config = self.config()
            result = refresh_fcm_registration(
                config,
                output_path=output,
                push_registrar=lambda auth, expo: calls.append((auth, expo)),
            )
            self.assertIs(result, config)
            self.assertEqual([("auth-token", "expo-token")], calls)
            self.assertTrue(config["facepunch_registered"])
            self.assertEqual(
                "temporary_pairing_receiver",
                config["receiver_registration_mode"],
            )

    def test_unregister_preserves_identity_and_credentials(self):
        calls = []
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fcm.json"
            config = self.config()
            config["facepunch_registered"] = True
            before = json.loads(json.dumps(config))
            result = unregister_fcm_registration(
                config,
                output_path=output,
                push_unregistrar=lambda auth, expo: calls.append((auth, expo)),
            )
            self.assertTrue(result)
            self.assertEqual([("auth-token", "expo-token")], calls)
            for key in (
                "fcm_credentials",
                "expo_push_token",
                "rustplus_auth_token",
                "device_id",
            ):
                self.assertEqual(before[key], config[key])
            self.assertFalse(config["facepunch_registered"])
            self.assertEqual("dormant_identity", config["receiver_registration_mode"])
            self.assertEqual(config, json.loads(output.read_text(encoding="utf-8")))

    def test_cleanup_skips_dormant_identity(self):
        config = self.config()
        config["facepunch_registered"] = False
        calls = []
        changed = cleanup_lingering_fcm_registration(
            config,
            push_unregistrar=lambda auth, expo: calls.append((auth, expo)),
        )
        self.assertFalse(changed)
        self.assertEqual([], calls)

    def test_pairing_listener_always_unregisters_after_success(self):
        config = self.config()
        lifecycle = []

        def activate(value, **_kwargs):
            lifecycle.append("register")
            value["facepunch_registered"] = True
            return value

        def deactivate(value, **_kwargs):
            lifecycle.append("unregister")
            value["facepunch_registered"] = False
            return True

        current = RustCredentials(host="203.0.113.10")
        _Inbox.instances.clear()
        with (
            patch.object(bootstrap, "_find_fcm_config", return_value=config),
            patch.object(bootstrap, "PairingNotificationInbox", _Inbox),
            patch.object(bootstrap, "refresh_fcm_registration", side_effect=activate),
            patch.object(bootstrap, "unregister_fcm_registration", side_effect=deactivate),
        ):
            source = bootstrap._listen_for_pairing(
                current,
                "203.0.113.10",
                _Finder(),
            )

        self.assertEqual("test", source)
        self.assertEqual(["register", "unregister"], lifecycle)
        self.assertEqual(-123, current.player_token)
        self.assertTrue(_Inbox.instances[0].drained)

    def test_pairing_listener_unregisters_when_no_record(self):
        class EmptyInbox(_Inbox):
            def wait_for(self, _host, **_kwargs):
                return None

        config = self.config()
        lifecycle = []

        def activate(value, **_kwargs):
            lifecycle.append("register")
            value["facepunch_registered"] = True
            return value

        def deactivate(value, **_kwargs):
            lifecycle.append("unregister")
            value["facepunch_registered"] = False
            return True

        with (
            patch.object(bootstrap, "_find_fcm_config", return_value=config),
            patch.object(bootstrap, "PairingNotificationInbox", EmptyInbox),
            patch.object(bootstrap, "refresh_fcm_registration", side_effect=activate),
            patch.object(bootstrap, "unregister_fcm_registration", side_effect=deactivate),
        ):
            source = bootstrap._listen_for_pairing(
                RustCredentials(host="203.0.113.10"),
                "203.0.113.10",
                _Finder(),
            )

        self.assertEqual("", source)
        self.assertEqual(["register", "unregister"], lifecycle)


if __name__ == "__main__":
    unittest.main()
