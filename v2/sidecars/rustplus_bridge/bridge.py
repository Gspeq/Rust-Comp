from __future__ import annotations
import json, sys, traceback
from typing import Any
from rust_companion_plus.models import RustCredentials
from rust_companion_plus.services.rustplus_client import RustPlusClient

SENSITIVE_KEYS = {"player_token", "token", "secret", "password", "api_key"}

def redact(value: Any) -> Any:
    if isinstance(value, dict): return {key: ("***" if key.casefold() in SENSITIVE_KEYS else redact(item)) for key, item in value.items()}
    if isinstance(value, list): return [redact(item) for item in value]
    return value

def dispatch(message: dict[str, Any], client: RustPlusClient | None = None) -> dict[str, Any]:
    command = str(message.get("command") or "").strip().casefold()
    if command == "health": return {"ok": True, "bridge": "rustplus-python", "protocol": 1}
    credentials = RustCredentials.from_dict(message.get("credentials") or {})
    if command == "credentials_summary": return {"ok": True, "credentials": redact(credentials.to_dict())}
    if not credentials.is_complete(): return {"ok": False, "error": "complete Rust+ credentials are required"}
    active_client = client or RustPlusClient()
    if command in {"snapshot", "team", "markers", "server"}:
        snapshot = active_client.fetch_snapshot(credentials)
        payload = snapshot.to_dict()
        if command == "team": payload = {"team": payload.get("team", [])}
        elif command == "markers": payload = {"markers": payload.get("markers", [])}
        elif command == "server": payload = {"server": payload.get("server", {}), "server_time": payload.get("server_time", "")}
        return {"ok": True, "payload": redact(payload)}
    return {"ok": False, "error": f"unsupported command: {command}"}

def main() -> int:
    for raw in sys.stdin:
        try:
            request = json.loads(raw)
            response = dispatch(request)
        except Exception as exc:
            response = {"ok": False, "error": str(exc), "type": type(exc).__name__}
            traceback.print_exc(file=sys.stderr)
        sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    return 0

if __name__ == "__main__": raise SystemExit(main())
