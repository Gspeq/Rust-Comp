from __future__ import annotations

import ipaddress
import os
import re
import socket
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


RUST_PROCESS_NAMES = {"rustclient.exe", "rustclient", "rust.exe", "rust"}
IGNORED_REMOTE_PORTS = {80, 443, 27017, 27018, 27019}
ENDPOINT_RE = re.compile(
    r"(?P<host>\[[0-9a-fA-F:]+\]|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}|(?:\d{1,3}\.){3}\d{1,3}|localhost)"
    r"\s*:\s*(?P<port>\d{2,5})"
)
CONTEXT_RE = re.compile(
    r"(?:client\.connect|steam://connect/|connect(?:ing|ed)?(?:\s+to)?|server\s+(?:address|endpoint)|raknet)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ServerCandidate:
    host: str
    port: int
    source: str
    confidence: int
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ServerDetectionError(RuntimeError):
    pass


def normalize_host(host: str) -> str:
    value = host.strip().strip("[]").lower()
    if value in {"localhost", "0.0.0.0", "::"}:
        return "127.0.0.1"
    return value


def parse_endpoint(text: str) -> tuple[str, int] | None:
    match = ENDPOINT_RE.search(text)
    if not match:
        return None
    host = normalize_host(match.group("host"))
    port = int(match.group("port"))
    if not 1 <= port <= 65535:
        return None
    try:
        if re.fullmatch(r"[0-9.]+", host):
            ipaddress.ip_address(host)
    except ValueError:
        return None
    return host, port


def default_rust_log_paths() -> list[Path]:
    paths: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        local = Path(local_app_data)
        paths.extend(
            [
                local.parent / "LocalLow" / "Facepunch Studios LTD" / "Rust" / "Player.log",
                local / "Facepunch Studios LTD" / "Rust" / "Player.log",
            ]
        )
    paths.append(Path.home() / "AppData" / "LocalLow" / "Facepunch Studios LTD" / "Rust" / "Player.log")
    return list(dict.fromkeys(paths))


def default_steam_history_paths() -> list[Path]:
    paths: list[Path] = []
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        base = os.environ.get(variable)
        if base:
            paths.append(Path(base) / "Steam" / "config" / "serverbrowser_hist.vdf")
    paths.append(Path.home() / "AppData" / "Local" / "Steam" / "config" / "serverbrowser_hist.vdf")
    return list(dict.fromkeys(paths))


def _tail_text(path: Path, max_bytes: int = 2_000_000) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        return handle.read().decode("utf-8", errors="replace")


def candidates_from_log(path: Path) -> list[ServerCandidate]:
    if not path.is_file():
        return []
    try:
        text = _tail_text(path)
    except OSError:
        return []

    matches: list[ServerCandidate] = []
    lines = text.splitlines()
    total = max(1, len(lines))
    for index, line in enumerate(lines):
        if not CONTEXT_RE.search(line):
            continue
        endpoint = parse_endpoint(line)
        if endpoint is None:
            continue
        host, port = endpoint
        recency_bonus = int(12 * (index / total))
        matches.append(
            ServerCandidate(host, port, "Rust Player.log", 72 + recency_bonus, line.strip()[-180:])
        )
    return matches


def candidates_from_steam_history(path: Path) -> list[ServerCandidate]:
    if not path.is_file():
        return []
    try:
        text = _tail_text(path, 1_000_000)
    except OSError:
        return []
    matches: list[ServerCandidate] = []
    for match in re.finditer(r'"(?:address|addr|ip)"\s+"([^"]+)"', text, re.IGNORECASE):
        endpoint = parse_endpoint(match.group(1))
        if endpoint:
            matches.append(ServerCandidate(*endpoint, "Steam server history", 35, path.name))
    return matches


def _safe_process_candidates() -> list[ServerCandidate]:
    try:
        import psutil
    except ImportError:
        return []

    results: list[ServerCandidate] = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = str(process.info.get("name") or "").lower()
            if name not in RUST_PROCESS_NAMES and not name.startswith("rustclient"):
                continue
            command = " ".join(str(item) for item in (process.info.get("cmdline") or []))
            if command:
                for match in ENDPOINT_RE.finditer(command):
                    prefix = command[max(0, match.start() - 40):match.start()]
                    if re.search(r"(?:\+?connect|steam://connect/)", prefix, re.IGNORECASE):
                        endpoint = parse_endpoint(match.group(0))
                        if endpoint:
                            results.append(
                                ServerCandidate(*endpoint, "Rust process command line", 100, f"PID {process.pid}")
                            )
            try:
                connections = process.net_connections(kind="inet")
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                connections = []
            for connection in connections:
                remote = getattr(connection, "raddr", None)
                if not remote:
                    continue
                host = normalize_host(str(getattr(remote, "ip", remote[0])))
                port = int(getattr(remote, "port", remote[1]))
                if port in IGNORED_REMOTE_PORTS or port < 1024:
                    continue
                status = str(getattr(connection, "status", ""))
                confidence = 92 if status.upper() == "ESTABLISHED" else 82
                results.append(
                    ServerCandidate(host, port, "Rust process network connection", confidence, f"PID {process.pid} {status}")
                )
        except Exception:
            continue
    return results


class ServerDetector:
    def __init__(
        self,
        *,
        log_paths: Iterable[Path] | None = None,
        steam_history_paths: Iterable[Path] | None = None,
        process_provider: Callable[[], list[ServerCandidate]] | None = None,
    ) -> None:
        self.log_paths = list(log_paths) if log_paths is not None else default_rust_log_paths()
        self.steam_history_paths = (
            list(steam_history_paths) if steam_history_paths is not None else default_steam_history_paths()
        )
        self.process_provider = process_provider or _safe_process_candidates

    def detect_all(self, preferred_host: str = "", preferred_port: int = 0) -> list[ServerCandidate]:
        candidates: list[ServerCandidate] = []
        candidates.extend(self.process_provider())
        for path in self.log_paths:
            candidates.extend(candidates_from_log(path))
        for path in self.steam_history_paths:
            candidates.extend(candidates_from_steam_history(path))
        if preferred_host:
            candidates.append(
                ServerCandidate(normalize_host(preferred_host), int(preferred_port or 0), "Saved Rust+ profile", 20)
            )

        deduped: dict[tuple[str, int], ServerCandidate] = {}
        for candidate in candidates:
            if not candidate.host:
                continue
            key = (normalize_host(candidate.host), int(candidate.port or 0))
            previous = deduped.get(key)
            if previous is None or candidate.confidence >= previous.confidence:
                deduped[key] = candidate
        return sorted(deduped.values(), key=lambda item: item.confidence, reverse=True)

    def detect(self, preferred_host: str = "", preferred_port: int = 0) -> ServerCandidate:
        candidates = self.detect_all(preferred_host, preferred_port)
        if not candidates:
            raise ServerDetectionError(
                "No active Rust server was detected. Launch/join Rust first, or keep a saved server profile as a fallback."
            )
        return candidates[0]


def hosts_equivalent(left: str, right: str) -> bool:
    left_norm, right_norm = normalize_host(left), normalize_host(right)
    if left_norm == right_norm:
        return True
    try:
        return socket.gethostbyname(left_norm) == socket.gethostbyname(right_norm)
    except OSError:
        return False
