from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any


REQUIRED_SOURCE_FILES = (
    "launcher.py",
    "main.py",
    "requirements.txt",
    "Run_Rust_Companion_Plus_Source.bat",
    "Build_Rust_Companion_Plus.bat",
)
ALLOWED_ROOT_BATCH_FILES = {
    "Run_Rust_Companion_Plus_Source.bat",
    "Build_Rust_Companion_Plus.bat",
}


def _issue(level: str, code: str, message: str) -> dict[str, str]:
    return {
        "level": level,
        "code": code,
        "message": message,
    }


def collect_bootstrap_issues(
    repo_root: Path | str,
    app_data_dir: Path | str,
    *,
    check_source_layout: bool = True,
    python_version: tuple[int, ...] | None = None,
) -> list[dict[str, str]]:
    """Return deterministic local bootstrap diagnostics without changing app data."""
    root = Path(repo_root)
    data_dir = Path(app_data_dir)
    version = tuple(python_version or sys.version_info[:3])
    issues: list[dict[str, str]] = []

    if version < (3, 11):
        issues.append(
            _issue(
                "fatal",
                "python_too_old",
                "Python 3.11 or newer is required for the source launcher.",
            )
        )

    package_dir = root / "rust_companion_plus"
    if check_source_layout:
        missing = [
            name
            for name in REQUIRED_SOURCE_FILES
            if not (root / name).is_file()
        ]
        if missing:
            issues.append(
                _issue(
                    "fatal",
                    "missing_source_files",
                    "Missing required source file(s): " + ", ".join(missing),
                )
            )
        if not package_dir.is_dir():
            issues.append(
                _issue(
                    "fatal",
                    "missing_package",
                    "The rust_companion_plus package directory is missing.",
                )
            )

        unexpected_batch = sorted(
            path.name
            for path in root.glob("*.bat")
            if path.name not in ALLOWED_ROOT_BATCH_FILES
        )
        if unexpected_batch:
            issues.append(
                _issue(
                    "warning",
                    "unexpected_root_launchers",
                    "Unexpected root batch file(s): "
                    + ", ".join(unexpected_batch),
                )
            )

        requirements = root / "requirements.txt"
        if requirements.is_file():
            meaningful = [
                line.strip()
                for line in requirements.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            if not meaningful:
                issues.append(
                    _issue(
                        "fatal",
                        "empty_requirements",
                        "requirements.txt contains no installable dependencies.",
                    )
                )

    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        if not data_dir.is_dir():
            raise OSError("path is not a directory")
        descriptor, raw_path = tempfile.mkstemp(
            prefix=".bootstrap-write-test-",
            suffix=".tmp",
            dir=data_dir,
        )
        os.close(descriptor)
        probe = Path(raw_path)
        probe.write_text("ok", encoding="utf-8")
        if probe.read_text(encoding="utf-8") != "ok":
            raise OSError("write verification failed")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        issues.append(
            _issue(
                "fatal",
                "app_data_unwritable",
                f"Application data directory is not writable: {exc}",
            )
        )

    return issues


def has_fatal_bootstrap_issue(issues: list[dict[str, Any]]) -> bool:
    return any(
        str(issue.get("level") or "").casefold() == "fatal"
        for issue in issues
    )


def format_bootstrap_report(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "BOOTSTRAP SELF-CHECK: OK"
    lines = ["BOOTSTRAP SELF-CHECK"]
    for issue in issues:
        lines.append(
            f"[{str(issue.get('level') or 'info').upper()}] "
            f"{issue.get('code')}: {issue.get('message')}"
        )
    return "\n".join(lines)
