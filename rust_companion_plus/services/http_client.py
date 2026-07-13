from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "Rust-Companion-Plus/0.3"


@dataclass(slots=True)
class ApiHttpError(RuntimeError):
    status: int
    message: str
    body: str = ""

    def __str__(self) -> str:
        return f"HTTP {self.status}: {self.message}"


def _url_with_query(url: str, query: Mapping[str, Any] | None) -> str:
    if not query:
        return url
    filtered = {key: value for key, value in query.items() if value not in (None, "")}
    if not filtered:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(filtered, doseq=True)}"


def request_json(
    method: str,
    url: str,
    *,
    query: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    payload: Any = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    target = _url_with_query(url, query)
    body: bytes | None = None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        **dict(headers or {}),
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = Request(target, data=body, headers=request_headers, method=method.upper())
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        message = exc.reason or "API request failed"
        try:
            parsed = json.loads(text)
            errors = parsed.get("errors") or parsed.get("meta", {}).get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict):
                    message = str(first.get("detail") or first.get("title") or message)
                else:
                    message = str(first)
        except (json.JSONDecodeError, AttributeError):
            pass
        raise ApiHttpError(exc.code, str(message), text) from exc
    except URLError as exc:
        raise ConnectionError(f"Could not reach {target}: {exc.reason}") from exc

    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"API returned invalid JSON from {target}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"API returned an unexpected JSON shape from {target}")
    return value


def download_file(
    url: str,
    destination: str | Path,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 45.0,
    max_bytes: int = 512 * 1024 * 1024,
) -> Path:
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    request_headers = {"User-Agent": USER_AGENT, **dict(headers or {})}
    request = Request(url, headers=request_headers, method="GET")

    temp_path: Path | None = None
    try:
        with urlopen(request, timeout=timeout) as response:
            length = int(response.headers.get("Content-Length", "0") or 0)
            if length > max_bytes:
                raise ValueError(f"Download is too large ({length:,} bytes).")
            fd, raw_temp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
            os.close(fd)
            temp_path = Path(raw_temp)
            written = 0
            with temp_path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError("Download exceeded the configured size limit.")
                    handle.write(chunk)
        temp_path.replace(target)
        return target
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise ApiHttpError(exc.code, str(exc.reason or "Download failed"), text) from exc
    except URLError as exc:
        raise ConnectionError(f"Could not download {url}: {exc.reason}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
