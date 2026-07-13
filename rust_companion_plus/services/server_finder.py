from __future__ import annotations

import ipaddress
import json
import os
import re
import urllib.error
import socket
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CONNECT_PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    (
        "rust_log_raknet",
        re.compile(
            r"(?im)(?P<timestamp>\d{4}-\d{2}-\d{2}T[^|\s]+)\|[^|\r\n]*\|Connecting:\s*"
            r"(?P<host>\[[0-9a-f:]+\]|[A-Za-z0-9._-]+):(?P<port>\d{1,5})\s*\(Raknet\)"
        ),
        0.99,
    ),
    (
        "rust_log_connect_command",
        re.compile(
            r"(?im)(?P<timestamp>\d{4}-\d{2}-\d{2}T[^|\s]+)\|[^|\r\n]*\|[^|\r\n]*?"
            r"(?:client\.connect|connect)\s+(?P<host>\[[0-9a-f:]+\]|[A-Za-z0-9._-]+):(?P<port>\d{1,5})"
        ),
        0.96,
    ),
)
DISCONNECT_RE = re.compile(
    r"(?im)(?P<timestamp>\d{4}-\d{2}-\d{2}T[^|\s]+)\|[^|\r\n]*\|"
    r"[^|\r\n]*?(?:Disconnected \(disconnect\)|returning to main menu)"
)
MAP_URL_RE = re.compile(r"https://maps\.rustmaps\.com/[^\s\"']+\.map", re.IGNORECASE)
WELCOME_RE = re.compile(r"Welcome to.*?(?:</size>|$)", re.IGNORECASE)


@dataclass(slots=True)
class ServerCandidate:
    host: str
    port: int
    source: str
    confidence: float
    observed_at: str = ""
    evidence: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["endpoint"] = self.endpoint
        return value


@dataclass(slots=True)
class DetectionReport:
    scanned_at: str
    selected: ServerCandidate | None = None
    candidates: list[ServerCandidate] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    debug: list[str] = field(default_factory=list)
    log_path: str = ""
    battlemetrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_at": self.scanned_at,
            "selected": self.selected.to_dict() if self.selected else None,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "rejected": self.rejected,
            "debug": self.debug,
            "log_path": self.log_path,
            "battlemetrics": self.battlemetrics,
            "warnings": self.warnings,
        }


class RustServerFinder:
    """Find the server Rust is actually joining and explain every decision.

    Evidence order is deliberate:
      1. Explicit ``Connecting: host:port (Raknet)`` lines in Rust's own log.
      2. Explicit client.connect lines in the same log.
      3. RustClient.exe *remote* sockets as a fallback only.

    Local/listening endpoints are never selected. This prevents helper sockets such
    as 127.0.0.1:32225 from being mistaken for a public Rust game server.
    """

    def __init__(self, store: Any | None = None, *, max_log_bytes: int = 8 * 1024 * 1024) -> None:
        self.store = store
        self.max_log_bytes = max_log_bytes

    def detect_once(self, *, enrich: bool = True) -> DetectionReport:
        report = DetectionReport(scanned_at=_now_iso())
        candidates: list[ServerCandidate] = []

        manual = self._manual_candidate()
        if manual is not None:
            candidates.append(manual)
            report.debug.append(f"manual override accepted as candidate: {manual.endpoint}")

        log_candidates, log_path, log_debug = self._scan_rust_logs()
        candidates.extend(log_candidates)
        report.log_path = str(log_path) if log_path else ""
        report.debug.extend(log_debug)

        socket_candidates, socket_debug = self._scan_rust_process_connections()
        candidates.extend(socket_candidates)
        report.debug.extend(socket_debug)

        accepted: list[ServerCandidate] = []
        seen: set[tuple[str, int, str]] = set()
        for candidate in candidates:
            rejection = self._rejection_reason(candidate)
            if rejection:
                report.rejected.append(
                    {
                        "endpoint": candidate.endpoint,
                        "source": candidate.source,
                        "reason": rejection,
                        "evidence": candidate.evidence,
                    }
                )
                report.debug.append(
                    f"rejected {candidate.endpoint} from {candidate.source}: {rejection}"
                )
                continue
            key = (candidate.host.casefold(), candidate.port, candidate.source)
            if key in seen:
                continue
            seen.add(key)
            accepted.append(candidate)

        accepted.sort(
            key=lambda item: (item.confidence, _timestamp_sort_value(item.observed_at)),
            reverse=True,
        )
        report.candidates = accepted
        selectable = [candidate for candidate in accepted if candidate.confidence >= 0.65]
        report.selected = selectable[0] if selectable else None
        for candidate in accepted:
            if candidate.confidence < 0.65:
                report.debug.append(
                    f"kept {candidate.endpoint} from {candidate.source} for diagnostics only; "
                    f"{candidate.confidence:.0%} is below the auto-selection threshold"
                )

        if report.selected:
            report.debug.append(
                f"selected {report.selected.endpoint} from {report.selected.source} "
                f"at {report.selected.confidence:.0%} confidence"
            )
            if enrich:
                self._enrich_with_battlemetrics(report)
            else:
                self._reuse_cached_enrichment(report)
        else:
            report.debug.append("no usable active Rust server endpoint found")

        if self.store is not None:
            self.store.set("server_detection", report.to_dict())
            if report.selected:
                self.store.set("detected_server", self._detected_server_payload(report))
        return report

    def _manual_candidate(self) -> ServerCandidate | None:
        if self.store is None:
            return None
        raw = str(self.store.get("manual_server_endpoint", "") or "").strip()
        parsed = _parse_endpoint(raw)
        if not parsed:
            return None
        host, port = parsed
        return ServerCandidate(
            host=host,
            port=port,
            source="manual_override",
            confidence=1.0,
            observed_at=_now_iso(),
            evidence="saved manual server endpoint",
        )

    def _scan_rust_logs(self) -> tuple[list[ServerCandidate], Path | None, list[str]]:
        debug: list[str] = []
        available = [path for path in self.discover_log_paths() if path.is_file()]
        if not available:
            debug.append("Rust log scan: no output_log.txt or Player.log found")
            return [], None, debug

        available.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in available:
            text = _read_tail(path, self.max_log_bytes)
            debug.append(
                f"Rust log scan: {path} ({len(text):,} decoded characters, "
                f"modified {datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec='seconds')})"
            )
            candidates, parse_debug = self._parse_log_text(text, path)
            debug.extend(parse_debug)
            if candidates:
                return candidates, path, debug
        return [], available[0], debug

    def _parse_log_text(self, text: str, path: Path) -> tuple[list[ServerCandidate], list[str]]:
        debug: list[str] = []
        disconnects = list(DISCONNECT_RE.finditer(text))
        last_disconnect_position = disconnects[-1].start() if disconnects else -1
        if disconnects:
            debug.append(
                f"latest disconnect marker: {disconnects[-1].groupdict().get('timestamp', 'unknown time')}"
            )

        map_urls = list(MAP_URL_RE.finditer(text))
        latest_map_url = map_urls[-1].group(0) if map_urls else ""
        if latest_map_url:
            debug.append(f"latest RustMaps world URL found: {latest_map_url}")

        matches: list[tuple[int, ServerCandidate]] = []
        for source, pattern, confidence in CONNECT_PATTERNS:
            for match in pattern.finditer(text):
                host = match.group("host").strip("[]")
                port = int(match.group("port"))
                timestamp = match.groupdict().get("timestamp", "")
                line = match.group(0).strip()
                metadata: dict[str, Any] = {"log_path": str(path)}
                if latest_map_url and map_urls[-1].start() >= match.start():
                    metadata["map_url"] = latest_map_url
                matches.append(
                    (
                        match.start(),
                        ServerCandidate(
                            host=host,
                            port=port,
                            source=source,
                            confidence=confidence,
                            observed_at=timestamp,
                            evidence=_truncate(line, 260),
                            metadata=metadata,
                        ),
                    )
                )

        if not matches:
            debug.append("Rust log parser: no explicit connection line found")
            return [], debug

        matches.sort(key=lambda pair: pair[0])
        latest_position, latest = matches[-1]
        debug.append(
            f"Rust log parser: latest explicit connection is {latest.endpoint} at "
            f"{latest.observed_at or 'unknown time'}"
        )
        if last_disconnect_position > latest_position:
            debug.append(
                "Rust log parser: that connection is stale because a later disconnect marker exists"
            )
            return [], debug

        # Only the latest active explicit connection is selectable. Older matches remain
        # visible in the debug count but cannot beat the active line.
        debug.append(f"Rust log parser: {len(matches)} total connection line(s) examined")
        return [latest], debug

    def discover_log_paths(self) -> list[Path]:
        paths: list[Path] = []

        configured = os.environ.get("RUST_LOG_PATH", "").strip()
        if configured:
            paths.append(Path(configured).expanduser())

        if self.store is not None:
            stored = str(self.store.get("rust_log_path", "") or "").strip()
            if stored:
                paths.append(Path(stored).expanduser())

        for root_name in ("ProgramFiles(x86)", "ProgramFiles"):
            root = os.environ.get(root_name)
            if root:
                paths.append(Path(root) / "Steam" / "steamapps" / "common" / "Rust" / "output_log.txt")

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            paths.append(
                Path(local_app_data)
                / ".."
                / "LocalLow"
                / "Facepunch Studios LTD"
                / "Rust"
                / "Player.log"
            )

        paths.extend(self._steam_library_log_paths())

        # The supplied log shows this exact default location. Keep it even when the
        # process environment omits ProgramFiles(x86), as can happen in packaged apps.
        paths.append(
            Path(r"C:\Program Files (x86)\Steam\steamapps\common\Rust\output_log.txt")
        )

        unique: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            normalized = str(path.resolve(strict=False)).casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(path)
        return unique

    def _steam_library_log_paths(self) -> list[Path]:
        results: list[Path] = []
        steam_roots: list[Path] = []
        try:
            import winreg  # type: ignore

            for hive, key_path in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        value, _ = winreg.QueryValueEx(key, "SteamPath" if hive == winreg.HKEY_CURRENT_USER else "InstallPath")
                        steam_roots.append(Path(str(value)))
                except OSError:
                    continue
        except (ImportError, OSError):
            pass

        for root in steam_roots:
            libraries = [root]
            vdf = root / "steamapps" / "libraryfolders.vdf"
            try:
                text = vdf.read_text(encoding="utf-8", errors="ignore")
                for value in re.findall(r'"path"\s+"([^"]+)"', text, re.IGNORECASE):
                    libraries.append(Path(value.replace("\\\\", "\\")))
            except OSError:
                pass
            for library in libraries:
                results.append(library / "steamapps" / "common" / "Rust" / "output_log.txt")
        return results

    def _scan_rust_process_connections(self) -> tuple[list[ServerCandidate], list[str]]:
        debug: list[str] = []
        try:
            import psutil  # type: ignore
        except ImportError:
            debug.append("process socket fallback unavailable: psutil is not installed")
            return [], debug

        candidates: list[ServerCandidate] = []
        rust_processes = []
        try:
            for process in psutil.process_iter(["pid", "name", "exe"]):
                name = str(process.info.get("name") or "").casefold()
                if name in {"rustclient.exe", "rust.exe"}:
                    rust_processes.append(process)
        except Exception as exc:
            debug.append(f"process scan failed: {exc}")
            return [], debug

        if not rust_processes:
            debug.append("process socket fallback: RustClient.exe is not running")
            return [], debug

        for process in rust_processes:
            debug.append(f"process socket fallback: examining Rust PID {process.pid}")
            try:
                connections = process.net_connections(kind="inet")
            except Exception as exc:
                debug.append(f"PID {process.pid}: unable to enumerate sockets ({exc})")
                continue
            for connection in connections:
                local = _address_tuple(connection.laddr)
                remote = _address_tuple(connection.raddr)
                status = str(getattr(connection, "status", "") or "")
                if not remote:
                    debug.append(
                        f"PID {process.pid}: ignored listening/local-only socket local={local or 'unknown'} status={status or 'NONE'}"
                    )
                    continue
                host, port = remote
                socket_type = "tcp" if getattr(connection, "type", 0) == socket.SOCK_STREAM else "udp"
                confidence = 0.76 if socket_type == "udp" and 20_000 <= port <= 40_000 else 0.58
                if port in {80, 443}:
                    confidence = 0.40
                candidate = ServerCandidate(
                    host=host,
                    port=port,
                    source="rust_process_remote_socket",
                    confidence=confidence,
                    observed_at=_now_iso(),
                    evidence=(
                        f"Rust PID {process.pid}; local={local or 'unknown'}; remote={host}:{port}; "
                        f"transport={socket_type}; status={status or 'NONE'}"
                    ),
                    metadata={"pid": process.pid, "local": local, "transport": socket_type, "status": status},
                )
                candidates.append(candidate)
                debug.append(
                    f"PID {process.pid}: remote candidate {candidate.endpoint} ({socket_type}, {confidence:.0%})"
                )
        return candidates, debug

    def _rejection_reason(self, candidate: ServerCandidate) -> str:
        if not (1 <= int(candidate.port) <= 65535):
            return "port is outside the valid range"
        host = candidate.host.strip().strip("[]")
        if not host:
            return "host is empty"
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return ""  # DNS hostnames are valid manual/log endpoints.
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if address.is_loopback:
            return "loopback address is a local helper socket, not a remote Rust server"
        if address.is_unspecified:
            return "unspecified/listening address cannot identify a server"
        if address.is_multicast:
            return "multicast address cannot identify a Rust game server"
        return ""


    def _reuse_cached_enrichment(self, report: DetectionReport) -> None:
        if self.store is None or report.selected is None:
            return
        previous = self.store.get("server_detection", {}) or {}
        previous_selected = previous.get("selected") or {}
        if previous_selected.get("endpoint") != report.selected.endpoint:
            return
        cached = previous.get("battlemetrics") or {}
        if cached:
            report.battlemetrics = dict(cached)
            report.warnings = list(previous.get("warnings") or [])
            report.debug.append("reused cached BattleMetrics enrichment for the unchanged endpoint")

    def _enrich_with_battlemetrics(self, report: DetectionReport) -> None:
        selected = report.selected
        if selected is None:
            return
        query = selected.endpoint
        params = urllib.parse.urlencode(
            {
                "filter[game]": "rust",
                "filter[search]": query,
                "page[size]": "20",
            }
        )
        request = urllib.request.Request(
            f"https://api.battlemetrics.com/servers?{params}",
            headers={"Accept": "application/json", "User-Agent": "Rust-Companion-Plus/0.2"},
        )
        token = ""
        if self.store is not None:
            token = str((self.store.get("api_keys", {}) or {}).get("battlemetrics", "") or "").strip()
        if token:
            request.add_header("Authorization", f"Bearer {token}")

        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            report.warnings.append(f"BattleMetrics enrichment failed: {exc}")
            report.debug.append(f"BattleMetrics query failed for {query}: {exc}")
            return

        rows = payload.get("data", []) if isinstance(payload, dict) else []
        exact_rows: list[dict[str, Any]] = []
        mismatches: list[str] = []
        for row in rows if isinstance(rows, list) else []:
            attributes = row.get("attributes", {}) if isinstance(row, dict) else {}
            ip = str(attributes.get("ip") or "").strip()
            port = _coerce_int(attributes.get("port"))
            query_port = _coerce_int(attributes.get("portQuery") or attributes.get("queryPort"))
            if ip == selected.host and selected.port in {port, query_port}:
                exact_rows.append(row)
            elif ip or port:
                mismatches.append(f"{ip}:{port or '?'} (query {query_port or '?'})")

        if not exact_rows:
            report.warnings.append(
                "BattleMetrics returned no exact IP/port match; enrichment was rejected instead of replacing the detected endpoint."
            )
            if mismatches:
                report.debug.append("BattleMetrics non-matching results: " + ", ".join(mismatches[:8]))
            return

        row = exact_rows[0]
        attributes = row.get("attributes", {})
        details = attributes.get("details", {}) if isinstance(attributes.get("details"), dict) else {}
        app_port = _find_int_by_key(details, ("rust_app_port", "rustappport", "app_port", "companion_port"))
        report.battlemetrics = {
            "id": str(row.get("id") or ""),
            "name": attributes.get("name") or "",
            "status": attributes.get("status") or "",
            "rank": attributes.get("rank"),
            "ip": attributes.get("ip") or selected.host,
            "port": _coerce_int(attributes.get("port")) or selected.port,
            "query_port": _coerce_int(attributes.get("portQuery") or attributes.get("queryPort")),
            "players": _coerce_int(attributes.get("players")),
            "max_players": _coerce_int(attributes.get("maxPlayers")),
            "queue": _coerce_int(details.get("rust_queued_players") or details.get("queuedPlayers")),
            "wipe": details.get("rust_last_wipe") or details.get("rust_last_wipe_time") or "",
            "next_wipe": details.get("rust_next_wipe") or "",
            "map": details.get("map") or details.get("rust_map_name") or "",
            "world_size": details.get("rust_world_size") or details.get("worldSize"),
            "seed": details.get("rust_world_seed") or details.get("seed"),
            "rust_app_port": app_port,
        }
        report.debug.append(
            f"BattleMetrics exact match accepted: ID {report.battlemetrics['id'] or '?'}; "
            f"{report.battlemetrics['ip']}:{report.battlemetrics['port']}"
        )
        if app_port:
            report.debug.append(f"BattleMetrics published Rust+ companion port {app_port}")
        else:
            report.warnings.append("Rust+ companion port was not published; it cannot be guessed from the game port.")

    def _detected_server_payload(self, report: DetectionReport) -> dict[str, Any]:
        assert report.selected is not None
        selected = report.selected
        battlemetrics = report.battlemetrics
        return {
            "host": selected.host,
            "game_port": selected.port,
            "endpoint": selected.endpoint,
            "source": selected.source,
            "confidence": selected.confidence,
            "observed_at": selected.observed_at,
            "scanned_at": report.scanned_at,
            "log_path": report.log_path,
            "map_url": selected.metadata.get("map_url", ""),
            "battlemetrics": battlemetrics,
            "rust_app_port": _coerce_int(battlemetrics.get("rust_app_port")),
            "warnings": report.warnings,
        }


def _read_tail(path: Path, maximum_bytes: int) -> str:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - maximum_bytes), os.SEEK_SET)
        return handle.read().decode("utf-8", errors="replace")


def _parse_endpoint(value: str) -> tuple[str, int] | None:
    value = value.strip()
    if not value:
        return None
    match = re.fullmatch(r"\[?(?P<host>[0-9A-Fa-f:.]+|[A-Za-z0-9._-]+)\]?:(?P<port>\d{1,5})", value)
    if not match:
        return None
    port = int(match.group("port"))
    if not 1 <= port <= 65535:
        return None
    return match.group("host"), port


def _address_tuple(value: Any) -> tuple[str, int] | None:
    if not value:
        return None
    try:
        host = str(value.ip)
        port = int(value.port)
        return host, port
    except AttributeError:
        pass
    try:
        host, port = value[0], value[1]
        return str(host), int(port)
    except (TypeError, IndexError, ValueError):
        return None


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _find_int_by_key(value: Any, keys: Iterable[str]) -> int:
    normalized_keys = {key.casefold().replace("-", "_") for key in keys}
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in normalized_keys:
                found = _coerce_int(child)
                if found:
                    return found
            found = _find_int_by_key(child, normalized_keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_int_by_key(child, normalized_keys)
            if found:
                return found
    return 0


def _timestamp_sort_value(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _truncate(value: str, length: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= length else value[: length - 1] + "…"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
