from __future__ import annotations

from pathlib import Path

try:
    from platformdirs import user_data_dir
except ImportError:  # Planning-only fallback
    user_data_dir = None


APP_NAME = "Rust Companion+"
APP_AUTHOR = "RustCompanionPlus"
PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"


def application_data_dir() -> Path:
    if user_data_dir is not None:
        path = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    else:
        path = Path.home() / ".rust_companion_plus"
    path.mkdir(parents=True, exist_ok=True)
    return path


APP_DATA_DIR = application_data_dir()
STORE_PATH = APP_DATA_DIR / "store.json"
