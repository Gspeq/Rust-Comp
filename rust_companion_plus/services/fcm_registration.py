from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from rust_companion_plus.config import APP_DATA_DIR, FCM_CONFIG_PATH
from rust_companion_plus.services.pairing import save_fcm_config

# Public identifiers used by the official Rust Companion Android application.
_API_KEY = "AIzaSyB5y2y-Tzqb4-I4Qnlsh_9naYv_TD8pCvY"
_PROJECT_ID = "rust-companion-app"
_GCM_SENDER_ID = "976529667804"
_GMS_APP_ID = "1:976529667804:android:d6f1ddeb4403b338fea619"
_ANDROID_PACKAGE_NAME = "com.facepunch.rust.companion"
_ANDROID_PACKAGE_CERT = "E28D05345FB78A7A1A63D70F4A302DBF426CA5AD"
_EXPO_TOKEN_URL = "https://exp.host/--/api/v2/push/getExpoPushToken"
_RUST_PUSH_REGISTER_URL = "https://companion-rust.facepunch.com:443/api/push/register"
_RUST_LOGIN_URL = "https://companion-rust.facepunch.com/login"

StatusCallback = Callable[[str], None]


class FCMRegistrationError(RuntimeError):
    """Raised when automatic Rust+ notification registration cannot finish."""


def request_or_register_fcm_config() -> dict[str, Any] | None:
    """First-run replacement for the launcher's manual config prompt."""
    print()
    print("RUST+ NOTIFICATION RECEIVER - AUTOMATIC FIRST-TIME SETUP")
    print("A private WebView2 window will open on the official Rust+ Steam sign-in page.")
    print("After sign-in, Rust Companion+ will register and save its notification receiver automatically.")
    try:
        return register_fcm_config(status=lambda message: print(f"[PAIRING SETUP] {message}"))
    except FCMRegistrationError as exc:
        print(f"[PAIRING SETUP FAILED] {exc}")
        print("Option A was cancelled. Correct the problem and select A again.")
        return None


def register_fcm_config(
    output_path: Path = FCM_CONFIG_PATH,
    *,
    timeout: float = 300.0,
    status: StatusCallback | None = None,
    android_register: Callable[[], dict[str, Any]] | None = None,
    expo_token_fetcher: Callable[[str], str] | None = None,
    auth_token_fetcher: Callable[[float], str] | None = None,
    push_registrar: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Create and save the FCM configuration used by PairingNotificationInbox."""
    announce = status or (lambda _message: None)
    android_register = android_register or _register_android_fcm
    expo_token_fetcher = expo_token_fetcher or _fetch_expo_push_token
    auth_token_fetcher = auth_token_fetcher or _capture_rustplus_auth_token
    push_registrar = push_registrar or _register_with_rust_plus

    announce("Registering a private notification receiver with FCM...")
    fcm_credentials = _call("FCM registration", android_register)
    fcm_token = _extract_fcm_token(fcm_credentials)

    announce("Requesting an Expo push token...")
    expo_push_token = _call("Expo token request", expo_token_fetcher, fcm_token)

    announce("Waiting for the official Rust+ Steam authorization...")
    rustplus_auth_token = _call("Rust+ Steam authorization", auth_token_fetcher, timeout)

    announce("Registering the receiver with Facepunch...")
    _call("Facepunch push registration", push_registrar, rustplus_auth_token, expo_push_token)

    config = {
        "fcm_credentials": fcm_credentials,
        "expo_push_token": expo_push_token,
        "rustplus_auth_token": rustplus_auth_token,
        "registered_by": "Rust Companion+",
    }
    save_fcm_config(output_path, config)
    try:
        os.chmod(output_path, 0o600)
    except OSError:
        pass
    announce(f"Notification receiver saved to {output_path}")
    return config


def _call(label: str, function: Callable[..., Any], *args: Any) -> Any:
    try:
        return function(*args)
    except FCMRegistrationError:
        raise
    except Exception as exc:
        raise FCMRegistrationError(f"{label} failed: {exc}") from exc


def _register_android_fcm() -> dict[str, Any]:
    try:
        from push_receiver.android_fcm_register import AndroidFCM
    except ImportError as exc:
        raise FCMRegistrationError(
            "rustPlusPushReceiver is unavailable. Reinstall the application dependencies."
        ) from exc
    credentials = AndroidFCM.register(
        _API_KEY,
        _PROJECT_ID,
        _GCM_SENDER_ID,
        _GMS_APP_ID,
        _ANDROID_PACKAGE_NAME,
        _ANDROID_PACKAGE_CERT,
    )
    if not isinstance(credentials, dict):
        raise FCMRegistrationError("FCM returned an unexpected registration response.")
    _extract_fcm_token(credentials)
    return credentials


def _extract_fcm_token(credentials: dict[str, Any]) -> str:
    fcm = credentials.get("fcm")
    token = fcm.get("token") if isinstance(fcm, dict) else None
    if not token or not str(token).strip():
        raise FCMRegistrationError("FCM registration did not return a device token.")
    return str(token).strip()


def _fetch_expo_push_token(fcm_token: str) -> str:
    payload = json.dumps(
        {
            "type": "fcm",
            "deviceId": str(uuid4()),
            "development": False,
            "appId": _ANDROID_PACKAGE_NAME,
            "deviceToken": fcm_token,
            "projectId": "49451aca-a822-41e6-ad59-955718d0ff9c",
        }
    ).encode("utf-8")
    response = _request_json(_EXPO_TOKEN_URL, payload)
    data = response.get("data")
    token = data.get("expoPushToken") if isinstance(data, dict) else None
    if not token or not str(token).strip():
        raise FCMRegistrationError("Expo did not return a push token.")
    return str(token).strip()


def _register_with_rust_plus(auth_token: str, expo_push_token: str) -> None:
    payload = json.dumps(
        {
            "AuthToken": auth_token,
            "DeviceId": "Rust Companion+",
            "PushKind": 3,
            "PushToken": expo_push_token,
        }
    ).encode("utf-8")
    _request_json(_RUST_PUSH_REGISTER_URL, payload, allow_empty=True)


def _request_json(url: str, payload: bytes, *, allow_empty: bool = False) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "RustCompanionPlus/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FCMRegistrationError(f"Remote service returned HTTP {exc.code}: {detail[:160]}") from exc
    except urllib.error.URLError as exc:
        raise FCMRegistrationError(f"Could not reach the remote service: {exc.reason}") from exc
    if not 200 <= status < 300:
        raise FCMRegistrationError(f"Remote service returned HTTP {status}: {raw[:160]}")
    if not raw.strip() and allow_empty:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        if allow_empty:
            return {}
        raise FCMRegistrationError("Remote service returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise FCMRegistrationError("Remote service returned an unexpected response.")
    return decoded


class _RustPlusAuthBridge:
    def __init__(self) -> None:
        self.window: Any = None
        self.token = ""
        self.finished = threading.Event()

    def capture(self, message: str) -> bool:
        try:
            payload = json.loads(message)
        except (TypeError, json.JSONDecodeError):
            return False
        token = payload.get("Token") if isinstance(payload, dict) else None
        current_url = self.window.get_current_url() if self.window is not None else ""
        host = (urlparse(current_url).hostname or "").casefold()
        if not token or not (host == "facepunch.com" or host.endswith(".facepunch.com")):
            return False
        self.token = str(token).strip()
        self.finished.set()
        if self.window is not None:
            self.window.destroy()
        return True


def _capture_rustplus_auth_token(timeout: float) -> str:
    try:
        import webview
    except ImportError as exc:
        raise FCMRegistrationError("pywebview is unavailable. Reinstall the application dependencies.") from exc

    bridge = _RustPlusAuthBridge()
    window = webview.create_window(
        "Rust Companion+ - Link Steam with Rust+",
        _RUST_LOGIN_URL,
        js_api=bridge,
        width=1100,
        height=780,
        min_size=(800, 600),
        confirm_close=True,
    )
    bridge.window = window

    def install_bridge(target: Any) -> None:
        target.evaluate_js(_bridge_script())

    def enforce_timeout() -> None:
        if not bridge.finished.wait(timeout) and bridge.window is not None:
            bridge.window.destroy()

    window.events.loaded += install_bridge
    timer = threading.Thread(target=enforce_timeout, name="rustplus-auth-timeout", daemon=True)
    timer.start()
    try:
        webview.start(
            gui="edgechromium",
            private_mode=True,
            storage_path=str(APP_DATA_DIR / "rustplus-webview"),
        )
    except Exception as exc:
        raise FCMRegistrationError(
            "The secure WebView2 login window could not start. Install or repair Microsoft Edge WebView2 Runtime."
        ) from exc
    if not bridge.token:
        raise FCMRegistrationError("Rust+ authorization was cancelled or timed out.")
    return bridge.token


def _bridge_script() -> str:
    return """
(function installRustPlusBridge() {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.capture) {
    window.ReactNativeWebView = {
      postMessage: function(message) {
        return window.pywebview.api.capture(message);
      }
    };
    return;
  }
  window.setTimeout(installRustPlusBridge, 50);
})();
"""
