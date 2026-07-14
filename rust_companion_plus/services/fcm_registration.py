from __future__ import annotations
from datetime import datetime, timezone

import contextlib
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
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
_DEFAULT_DEVICE_ID = "rustplus.py"


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
    rustplus_auth_token = _call(
        "Rust+ Steam authorization",
        auth_token_fetcher,
        timeout,
    )

    announce("Registering the receiver with Facepunch...")
    _call(
        "Facepunch push registration",
        push_registrar,
        rustplus_auth_token,
        expo_push_token,
    )

    config = {
        "fcm_credentials": fcm_credentials,
        "expo_push_token": expo_push_token,
        "rustplus_auth_token": rustplus_auth_token,
        "device_id": _DEFAULT_DEVICE_ID,
        "registered_by": "Rust Companion+",
        "registered_at": datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds"),
        "receiver_registration_mode": "new_identity",
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

    # The upstream library prints PHONE_REGISTRATION_ERROR for transient attempts,
    # even when a later built-in retry succeeds. Keep the console clear unless the
    # complete registration operation actually fails.
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            credentials = AndroidFCM.register(
                _API_KEY,
                _PROJECT_ID,
                _GCM_SENDER_ID,
                _GMS_APP_ID,
                _ANDROID_PACKAGE_NAME,
                _ANDROID_PACKAGE_CERT,
            )
    except Exception as exc:
        diagnostic = output.getvalue().strip()
        if "PHONE_REGISTRATION_ERROR" in diagnostic:
            raise FCMRegistrationError(
                "Google rejected the virtual notification receiver after all retries. "
                "Wait a few minutes and select A again."
            ) from exc
        raise

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


def _register_with_rust_plus(
    auth_token: str,
    expo_push_token: str,
) -> None:
    payload = json.dumps(
        {
            "AuthToken": auth_token,
            "DeviceId": _DEFAULT_DEVICE_ID,
            "PushKind": 3,
            "PushToken": expo_push_token,
        }
    ).encode("utf-8")
    _request_json(
        _RUST_PUSH_REGISTER_URL,
        payload,
        allow_empty=True,
    )




def refresh_fcm_registration(
    config: dict[str, Any],
    *,
    output_path: Path = FCM_CONFIG_PATH,
    status: StatusCallback | None = None,
    push_registrar: Callable[[str, str], None] | None = None,
) -> dict[str, Any] | None:
    # Re-register the existing desktop push identity with Facepunch.
    # No FCM, Expo, Steam authorization, or phone identity is regenerated.
    announce = status or (lambda _message: None)
    registrar = push_registrar or _register_with_rust_plus

    auth_token = str(
        config.get("rustplus_auth_token") or ""
    ).strip()
    expo_push_token = str(
        config.get("expo_push_token") or ""
    ).strip()

    if not auth_token or not expo_push_token:
        announce(
            "Saved receiver registration is incomplete; "
            "full setup is required."
        )
        return None

    # Older rustplus.py-compatible configs require this stable label even
    # though Facepunch registration itself only uses the Expo push token.
    config["device_id"] = str(
        config.get("device_id") or _DEFAULT_DEVICE_ID
    )
    config["registered_by"] = str(
        config.get("registered_by") or "Rust Companion+"
    )

    announce("Refreshing this desktop receiver with Facepunch...")
    _call(
        "Facepunch push registration refresh",
        registrar,
        auth_token,
        expo_push_token,
    )

    config["last_facepunch_refresh"] = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")
    config["last_facepunch_refresh_status"] = "confirmed"
    config["receiver_registration_mode"] = "existing_identity_refresh"

    save_fcm_config(output_path, config)
    try:
        resolved_output = Path(output_path)
        if resolved_output.exists():
            resolved_output.chmod(0o600)
    except OSError:
        pass

    announce(
        "Desktop receiver registration confirmed. "
        "The official phone pairing was not changed."
    )
    return config






def _request_json(
    url: str,
    payload: bytes,
    *,
    allow_empty: bool = False,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "RustCompanionPlus/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FCMRegistrationError(
            f"Remote service returned HTTP {exc.code}: {detail[:160]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise FCMRegistrationError(
            f"Could not reach the remote service: {exc.reason}"
        ) from exc

    if not 200 <= status < 300:
        raise FCMRegistrationError(
            f"Remote service returned HTTP {status}: {raw[:160]}"
        )
    if not raw.strip():
        if allow_empty:
            return {}
        raise FCMRegistrationError(
            "Remote service returned an empty response."
        )

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FCMRegistrationError(
            f"Remote service returned invalid JSON: {raw[:160]}"
        ) from exc
    if not isinstance(decoded, dict):
        raise FCMRegistrationError(
            "Remote service returned an unexpected response."
        )
    return decoded



class _RustPlusAuthBridge:
    """Minimal JS callback target.

    This method deliberately performs no WebView operations. Calling window APIs or
    destroying the window from inside a pywebview JS callback can deadlock WebView2.
    """

    def __init__(self) -> None:
        self.token = ""
        self.token_ready = threading.Event()

    def capture(self, message: str) -> bool:
        try:
            payload = json.loads(message)
        except (TypeError, json.JSONDecodeError):
            return False
        token = payload.get("Token") if isinstance(payload, dict) else None
        if not token or not str(token).strip():
            return False
        self.token = str(token).strip()
        self.token_ready.set()
        return True


def _capture_rustplus_auth_token(timeout: float) -> str:
    try:
        import webview
    except ImportError as exc:
        raise FCMRegistrationError("pywebview is unavailable. Reinstall the application dependencies.") from exc

    bridge = _RustPlusAuthBridge()
    window_closed = threading.Event()
    timed_out = threading.Event()

    window = webview.create_window(
        "Rust Companion+ - Link Steam with Rust+",
        _RUST_LOGIN_URL,
        js_api=bridge,
        width=1100,
        height=780,
        min_size=(800, 600),
        confirm_close=False,
    )

    def install_bridge(*_event_args: Any) -> None:
        try:
            # pywebview versions differ: some loaded events pass the window,
            # while others pass no arguments. Use the closed-over window.
            window.evaluate_js(_bridge_script())
        except Exception:
            # A redirect can invalidate the old page while the loaded event is firing.
            # The next Facepunch page load will install the bridge again.
            return

    def note_closed() -> None:
        window_closed.set()

    def close_after_result() -> None:
        deadline = time.monotonic() + timeout
        while not window_closed.is_set():
            if bridge.token_ready.wait(0.1):
                # Let the JS API call return before touching the native window.
                time.sleep(0.35)
                if not window_closed.is_set():
                    try:
                        window.destroy()
                    except Exception:
                        pass
                return
            if time.monotonic() >= deadline:
                timed_out.set()
                try:
                    window.destroy()
                except Exception:
                    pass
                return

    window.events.loaded += install_bridge
    window.events.closed += note_closed
    closer = threading.Thread(target=close_after_result, name="rustplus-auth-window-closer", daemon=True)
    closer.start()

    try:
        webview.start(
            gui="edgechromium",
            private_mode=True,
            storage_path=str(APP_DATA_DIR / "rustplus-webview"),
        )
    except Exception as exc:
        raise FCMRegistrationError(
            "The WebView2 login window could not start. Install or repair Microsoft Edge WebView2 Runtime."
        ) from exc

    if bridge.token:
        return bridge.token
    if timed_out.is_set():
        raise FCMRegistrationError("Rust+ authorization timed out after five minutes.")
    raise FCMRegistrationError("Rust+ authorization window was closed before sign-in completed.")


def _bridge_script() -> str:
    # The host restriction is enforced in the page itself, so the Python callback
    # never needs to synchronously query the WebView URL.
    return r"""
(function installRustPlusBridge() {
  const host = String(window.location.hostname || '').toLowerCase();
  const isFacepunch = host === 'facepunch.com' || host.endsWith('.facepunch.com');
  if (!isFacepunch) {
    return;
  }
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.capture)) {
    window.setTimeout(installRustPlusBridge, 25);
    return;
  }
  const bridge = {
    postMessage: function(message) {
      window.pywebview.api.capture(String(message)).catch(function() {});
    }
  };
  try {
    Object.defineProperty(window, 'ReactNativeWebView', {
      configurable: true,
      enumerable: true,
      writable: true,
      value: bridge
    });
  } catch (_) {
    window.ReactNativeWebView = bridge;
  }
})();
"""
