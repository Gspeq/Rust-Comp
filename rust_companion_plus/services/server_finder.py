from __future__ import annotations
import hashlib
import base64

import ipaddress
import json
import os
import re
import urllib.error
import socket
import struct
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
APP_PORT_RE = re.compile(
    r"(?im)(?:(?P<timestamp>\d{4}-\d{2}-\d{2}T[^|\s]+)\|[^\r\n]*\|[^\r\n]*?)?"
    r"(?:\bapp\.port\b|\brust_app_port\b|\brustappport\b|"
    r"\bcompanion(?:/app)?[ _.-]*port\b)\s*(?:[:=]|\bis\b)?\s*(?P<port>\d{1,5})"
)
APP_PORT_KEYS = (
    "rust_app_port",
    "rustappport",
    "app_port",
    "app.port",
    "companion_port",
    "companionport",
)


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
    rust_app_port: int = 0
    rust_app_port_source: str = ""
    a2s_rules: dict[str, str] = field(default_factory=dict)
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
            "rust_app_port": self.rust_app_port,
            "rust_app_port_source": self.rust_app_port_source,
            "a2s_rules": self.a2s_rules,
            "warnings": self.warnings,
        }


@dataclass(slots=True)
class RustProcessSession:
    running: bool
    pids: list[int] = field(default_factory=list)
    started_at_epoch: float = 0.0
    started_at: str = ""
    debug: list[str] = field(default_factory=list)


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

    def detect_once(
        self,
        *,
        enrich: bool = True,
        require_running_process: bool = False,
        session_started_at: float | None = None,
        current_session_only: bool = False,
    ) -> DetectionReport:
        report = DetectionReport(scanned_at=_now_iso())
        candidates: list[ServerCandidate] = []

        process_session: RustProcessSession | None = None
        if require_running_process:
            process_session = self.get_rust_process_session()
            report.debug.extend(process_session.debug)
            if not process_session.running:
                report.debug.append(
                    "current-session gate: RustClient.exe is not running; saved log connections were suppressed"
                )
                report.debug.append("no usable active Rust server endpoint found")
                if self.store is not None:
                    self.store.set("server_detection", report.to_dict())
                    self.store.set("detected_server", {})
                return report
            if session_started_at is None:
                session_started_at = process_session.started_at_epoch
            report.debug.append(
                f"current-session gate: Rust is running as PID(s) {', '.join(str(pid) for pid in process_session.pids)}; "
                f"accepting log events from {process_session.started_at or 'the current process session'} onward"
            )

        if not current_session_only:
            manual = self._manual_candidate()
            if manual is not None:
                candidates.append(manual)
                report.debug.append(f"manual override accepted as candidate: {manual.endpoint}")
        else:
            report.debug.append("current-session gate: manual overrides are diagnostics-only during launcher auto-detection")

        log_candidates, log_path, log_debug = self._scan_rust_logs(
            not_before_epoch=session_started_at if current_session_only else None
        )
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
                self._resolve_rust_app_port(report)
            else:
                self._reuse_cached_enrichment(report)
        else:
            report.debug.append("no usable active Rust server endpoint found")

        if self.store is not None:
            self.store.set("server_detection", report.to_dict())
            if report.selected:
                self.store.set("detected_server", self._detected_server_payload(report))
            elif require_running_process:
                self.store.set("detected_server", {})
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

    def _scan_rust_logs(
        self, *, not_before_epoch: float | None = None
    ) -> tuple[list[ServerCandidate], Path | None, list[str]]:
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
            candidates, parse_debug = self._parse_log_text(
                text, path, not_before_epoch=not_before_epoch
            )
            debug.extend(parse_debug)
            if candidates:
                return candidates, path, debug
        return [], available[0], debug

    def _parse_log_text(
        self, text: str, path: Path, *, not_before_epoch: float | None = None
    ) -> tuple[list[ServerCandidate], list[str]]:
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

        total_matches = len(matches)
        if not_before_epoch is not None and matches:
            # Rust log timestamps are UTC. A small tolerance allows the process and
            # first log line to be recorded in either order during startup.
            threshold = max(0.0, float(not_before_epoch) - 15.0)
            current_session_matches: list[tuple[int, ServerCandidate]] = []
            for position, candidate in matches:
                observed_epoch = _timestamp_sort_value(candidate.observed_at)
                if not observed_epoch:
                    debug.append(
                        f"Rust log parser: rejected {candidate.endpoint} because its timestamp "
                        "could not be tied to the current Rust process session"
                    )
                    continue
                if observed_epoch < threshold:
                    debug.append(
                        f"Rust log parser: rejected stale previous-session connection "
                        f"{candidate.endpoint} at {candidate.observed_at}"
                    )
                    continue
                current_session_matches.append((position, candidate))
            matches = current_session_matches
            debug.append(
                f"Rust log parser: {len(matches)}/{total_matches} connection line(s) belong to "
                "the current Rust process session"
            )

        if not matches:
            if not_before_epoch is not None and total_matches:
                debug.append("Rust log parser: no current-session connection line found yet")
            else:
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

        app_port_matches = list(APP_PORT_RE.finditer(text))
        if app_port_matches:
            threshold = max(0.0, float(not_before_epoch or 0.0) - 15.0)
            usable_ports: list[tuple[int, int, str]] = []
            for port_match in app_port_matches:
                port = _coerce_int(port_match.groupdict().get("port"))
                timestamp = port_match.groupdict().get("timestamp", "") or ""
                observed_epoch = _timestamp_sort_value(timestamp)
                if not 1 <= port <= 65535:
                    continue
                if not_before_epoch is not None and timestamp and observed_epoch < threshold:
                    continue
                usable_ports.append((port_match.start(), port, timestamp))
            if usable_ports:
                _, app_port, app_timestamp = usable_ports[-1]
                latest.metadata["rust_app_port"] = app_port
                latest.metadata["rust_app_port_source"] = "rust_log"
                latest.metadata["rust_app_port_observed_at"] = app_timestamp
                debug.append(f"Rust log parser: companion port {app_port} found in the current log session")

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

    def get_rust_process_session(self) -> RustProcessSession:
        """Return the active Rust client session without consulting stale log files."""
        try:
            import psutil  # type: ignore
        except ImportError:
            return RustProcessSession(
                running=False,
                debug=["Rust process gate unavailable: psutil is not installed"],
            )

        rows: list[tuple[int, str, float]] = []
        debug: list[str] = []
        try:
            for process in psutil.process_iter(["pid", "name", "exe", "create_time"]):
                name = str(process.info.get("name") or "").casefold()
                if name not in {"rustclient.exe", "rust.exe"}:
                    continue
                try:
                    created = float(process.info.get("create_time") or process.create_time())
                except Exception:
                    created = 0.0
                rows.append((int(process.pid), name, created))
        except Exception as exc:
            return RustProcessSession(
                running=False,
                debug=[f"Rust process gate failed while enumerating processes: {exc}"],
            )

        if not rows:
            return RustProcessSession(
                running=False,
                debug=["Rust process gate: RustClient.exe is not running"],
            )

        primary = [row for row in rows if row[1] == "rustclient.exe"] or rows
        valid_start_times = [row[2] for row in primary if row[2] > 0]
        started_at_epoch = min(valid_start_times) if valid_start_times else 0.0
        started_at = ""
        if started_at_epoch:
            started_at = datetime.fromtimestamp(
                started_at_epoch, timezone.utc
            ).isoformat(timespec="seconds")
        pids = sorted(row[0] for row in primary)
        debug.append(
            f"Rust process gate: live Rust session found; PID(s) {', '.join(str(pid) for pid in pids)}; "
            f"started {started_at or 'at an unknown time'}"
        )
        return RustProcessSession(
            running=True,
            pids=pids,
            started_at_epoch=started_at_epoch,
            started_at=started_at,
            debug=debug,
        )

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
            report.rust_app_port = _coerce_int(previous.get("rust_app_port"))
            report.rust_app_port_source = str(previous.get("rust_app_port_source") or "")
            report.a2s_rules = dict(previous.get("a2s_rules") or {})
            report.debug.append("reused cached BattleMetrics/Rust+ enrichment for the unchanged endpoint")

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

    def _resolve_rust_app_port(
        self,
        report: DetectionReport,
    ) -> None:
        selected = report.selected
        if selected is None:
            return

        log_port = _coerce_int(selected.metadata.get("rust_app_port"))
        if log_port:
            report.rust_app_port = log_port
            report.rust_app_port_source = str(
                selected.metadata.get("rust_app_port_source") or "rust_log"
            )
            report.debug.append(
                f"Rust+ companion port {log_port} accepted from "
                f"{report.rust_app_port_source}"
            )
            return

        battlemetrics_port = _coerce_int(
            report.battlemetrics.get("rust_app_port")
        )
        if battlemetrics_port:
            report.rust_app_port = battlemetrics_port
            report.rust_app_port_source = "battlemetrics_exact_match"
            report.debug.append(
                "Rust+ companion port "
                f"{battlemetrics_port} accepted from the exact "
                "BattleMetrics server record"
            )
            return

        query_ports: list[int] = []
        for value in (
            report.battlemetrics.get("query_port"),
            report.battlemetrics.get("port"),
            selected.metadata.get("query_port"),
            selected.port,
        ):
            port = _coerce_int(value)
            if 1 <= port <= 65535 and port not in query_ports:
                query_ports.append(port)

        for query_port in query_ports:
            try:
                rules = _query_a2s_rules(selected.host, query_port)
            except (OSError, ValueError) as exc:
                report.debug.append(
                    "A2S rules query failed for "
                    f"{selected.host}:{query_port}: {exc}"
                )
                continue
            if not rules:
                report.debug.append(
                    "A2S rules query returned no rules for "
                    f"{selected.host}:{query_port}"
                )
                continue

            report.a2s_rules = rules
            app_port = _find_int_by_key(rules, APP_PORT_KEYS)
            if app_port:
                report.rust_app_port = app_port
                report.rust_app_port_source = f"a2s_rules:{query_port}"
                report.debug.append(
                    "Rust+ companion port "
                    f"{app_port} discovered through A2S_RULES "
                    f"on query port {query_port}"
                )
                return
            report.debug.append(
                "A2S rules were readable on "
                f"{query_port}, but no Rust+ app-port rule was published"
            )

        official_candidate = int(selected.port) + 67
        if 10000 <= official_candidate <= 65535:
            report.debug.append(
                "Rust+ official-default candidate: "
                f"{selected.host}:{official_candidate} "
                "(game port + 67); starting one WebSocket probe"
            )
            succeeded, detail = _probe_rustplus_websocket(
                selected.host,
                official_candidate,
            )
            report.debug.append(
                "Rust+ official-default WebSocket probe "
                f"{'succeeded' if succeeded else 'failed'} for "
                f"{selected.host}:{official_candidate}: {detail}"
            )
            if succeeded:
                report.rust_app_port = official_candidate
                report.rust_app_port_source = (
                    "facepunch_default_plus_67_websocket_probe"
                )
                return
        else:
            report.debug.append(
                "Rust+ official-default candidate was invalid: "
                f"game port {selected.port} + 67"
            )

        report.warnings.append(
            "Rust+ companion port was not published in the current "
            "log, exact BattleMetrics record, or A2S rules, and the "
            "verified Facepunch default candidate did not respond as "
            "a WebSocket. Pairing data remains authoritative."
        )


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
            "rust_app_port": report.rust_app_port,
            "rust_app_port_source": report.rust_app_port_source,
            "a2s_rules": report.a2s_rules,
            "warnings": report.warnings,
        }


def _probe_rustplus_websocket(
    host: str,
    port: int,
    *,
    timeout: float = 1.75,
) -> tuple[bool, str]:
    if not host or not 10000 <= int(port) <= 65535:
        return False, "candidate is outside Rust+ port requirements"

    key = base64.b64encode(os.urandom(16)).decode("ascii")
    expected_accept = base64.b64encode(
        hashlib.sha1(
            (
                key
                + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            ).encode("ascii")
        ).digest()
    ).decode("ascii")
    request = (
        "GET / HTTP/1.1\r\n"
        f"Host: {host}:{int(port)}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "User-Agent: RustCompanionPlus/0.3\r\n"
        "\r\n"
    ).encode("ascii")

    last_error = "no address succeeded"
    try:
        addresses = socket.getaddrinfo(
            host,
            int(port),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        return False, f"DNS/address resolution failed: {exc}"

    for family, socktype, protocol, _, address in addresses:
        try:
            with socket.socket(family, socktype, protocol) as client:
                client.settimeout(timeout)
                client.connect(address)
                client.sendall(request)
                response = client.recv(4096)
        except OSError as exc:
            last_error = str(exc)
            continue

        header = response.decode("latin-1", errors="replace")
        lines = header.splitlines()
        first_line = lines[0] if lines else ""
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().casefold()] = value.strip()

        if " 101 " not in f" {first_line} ":
            last_error = first_line or "no HTTP status received"
            continue
        if headers.get("upgrade", "").casefold() != "websocket":
            last_error = "HTTP 101 lacked Upgrade: websocket"
            continue
        if "upgrade" not in headers.get("connection", "").casefold():
            last_error = "HTTP 101 lacked Connection: Upgrade"
            continue
        if headers.get("sec-websocket-accept", "") != expected_accept:
            last_error = "HTTP 101 returned an invalid Sec-WebSocket-Accept"
            continue
        return True, f"{first_line}; WebSocket accept key verified"

    return False, last_error


def _query_a2s_rules(host: str, port: int, *, timeout: float = 1.75) -> dict[str, str]:
    """Read Source A2S_RULES without scanning or guessing arbitrary ports."""
    if not host or not 1 <= int(port) <= 65535:
        raise ValueError("invalid A2S host or port")

    last_error: OSError | None = None
    addresses = socket.getaddrinfo(host, int(port), type=socket.SOCK_DGRAM)
    for family, socktype, protocol, _, address in addresses:
        try:
            with socket.socket(family, socktype, protocol) as client:
                client.settimeout(timeout)
                client.sendto(b"\xff\xff\xff\xffV\xff\xff\xff\xff", address)
                response = _receive_a2s_payload(client)
                if len(response) >= 9 and response[:5] == b"\xff\xff\xff\xffA":
                    challenge = response[5:9]
                    client.sendto(b"\xff\xff\xff\xffV" + challenge, address)
                    response = _receive_a2s_payload(client)
                return _parse_a2s_rules(response)
        except OSError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return {}


def _receive_a2s_payload(client: socket.socket) -> bytes:
    first, _ = client.recvfrom(65535)
    if first.startswith(b"\xff\xff\xff\xff"):
        return first
    if not first.startswith(b"\xfe\xff\xff\xff") or len(first) < 10:
        return first

    request_id = struct.unpack_from("<I", first, 4)[0]
    if request_id & 0x80000000:
        raise OSError("compressed split A2S responses are not supported")
    total = first[8]
    number = first[9]
    if not total or number >= total:
        raise OSError("invalid split A2S response header")
    offset = 12 if len(first) >= 12 else 10
    parts: dict[int, bytes] = {number: first[offset:]}

    while len(parts) < total:
        packet, _ = client.recvfrom(65535)
        if not packet.startswith(b"\xfe\xff\xff\xff") or len(packet) < 10:
            continue
        packet_id = struct.unpack_from("<I", packet, 4)[0]
        if packet_id != request_id:
            continue
        packet_total = packet[8]
        packet_number = packet[9]
        if packet_total != total or packet_number >= total:
            continue
        packet_offset = 12 if len(packet) >= 12 else 10
        parts[packet_number] = packet[packet_offset:]
    return b"".join(parts[index] for index in range(total))


def _parse_a2s_rules(payload: bytes) -> dict[str, str]:
    if len(payload) < 7 or payload[:5] != b"\xff\xff\xff\xffE":
        return {}
    count = struct.unpack_from("<H", payload, 5)[0]
    position = 7
    rules: dict[str, str] = {}
    for _ in range(count):
        key, position = _read_cstring(payload, position)
        value, position = _read_cstring(payload, position)
        if key:
            rules[key] = value
        if position >= len(payload):
            break
    return rules


def _read_cstring(payload: bytes, position: int) -> tuple[str, int]:
    if position >= len(payload):
        return "", len(payload)
    end = payload.find(b"\x00", position)
    if end < 0:
        end = len(payload)
        next_position = len(payload)
    else:
        next_position = end + 1
    return payload[position:end].decode("utf-8", errors="replace"), next_position


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
