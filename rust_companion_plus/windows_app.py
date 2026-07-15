from __future__ import annotations

import json
import logging
import sys
import tempfile
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import messagebox
from typing import Sequence

from rust_companion_plus.config import APP_DATA_DIR, LOG_DIR
from rust_companion_plus.version import __version__


_LOGGER = logging.getLogger("rust_companion_plus")


def configure_application_logging() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "RustCompanionPlus.log"

    if not any(
        isinstance(handler, RotatingFileHandler)
        for handler in _LOGGER.handlers
    ):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=4,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s "
                "%(name)s: %(message)s"
            )
        )
        _LOGGER.addHandler(handler)
        _LOGGER.setLevel(logging.INFO)

    return log_path


def _install_exception_hook() -> None:
    def hook(
        exception_type: type[BaseException],
        exception: BaseException,
        tb: object,
    ) -> None:
        _LOGGER.error(
            "Unhandled application exception",
            exc_info=(exception_type, exception, tb),
        )
        try:
            messagebox.showerror(
                "Rust Companion+ stopped unexpectedly",
                (
                    f"{exception}\n\n"
                    "A production log was saved under the Rust "
                    "Companion+ LocalAppData folder."
                ),
            )
        except Exception:
            traceback.print_exception(
                exception_type,
                exception,
                tb,
            )

    sys.excepthook = hook


def packaged_self_test() -> int:
    imports: dict[str, str] = {}
    for module_name in (
        "customtkinter",
        "PIL",
        "platformdirs",
        "psutil",
        "rustplus",
        "rustmap_parser",
        "webview",
        "push_receiver",
    ):
        try:
            module = __import__(module_name)
        except Exception as exc:
            imports[module_name] = (
                f"failed: {type(exc).__name__}: {exc}"
            )
        else:
            imports[module_name] = str(
                getattr(module, "__version__", "available")
            )

    writable = False
    try:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix="self-test-",
            suffix=".tmp",
            dir=APP_DATA_DIR,
            delete=True,
        ):
            writable = True
    except OSError:
        writable = False

    payload = {
        "application": "Rust Companion+",
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": str(Path(sys.executable).resolve()),
        "app_data_dir": str(APP_DATA_DIR),
        "app_data_writable": writable,
        "imports": imports,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    failed_imports = [
        name
        for name, value in imports.items()
        if value.startswith("failed:")
    ]
    return 0 if writable and not failed_imports else 1


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(
        sys.argv[1:] if argv is None else argv
    )
    configure_application_logging()
    _install_exception_hook()

    if "--self-test" in arguments:
        return packaged_self_test()

    if "--uninstall" in arguments:
        from rust_companion_plus.windows_integration import (
            request_uninstall,
        )

        return 0 if request_uninstall() else 1

    _LOGGER.info(
        "Starting Rust Companion+ %s; frozen=%s",
        __version__,
        bool(getattr(sys, "frozen", False)),
    )

    try:
        from rust_companion_plus.bootstrap import main as bootstrap_main

        return int(bootstrap_main() or 0)
    except KeyboardInterrupt:
        _LOGGER.info("Application cancelled by user.")
        return 130
    except Exception:
        _LOGGER.exception("Application startup failed.")
        raise
