from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from rust_companion_plus.config import DATA_DIR


@lru_cache(maxsize=1)
def electrical_catalog() -> dict[str, dict[str, Any]]:
    path = DATA_DIR / "electrical_components.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {row["name"]: row for row in rows}


RECYCLE_CATALOG: dict[str, dict[str, float]] = {
    "Tech Trash": {"Scrap": 20.0, "High Quality Metal": 1.0},
    "Gears": {"Scrap": 10.0, "Metal Fragments": 13.0},
    "Sheet Metal": {"Scrap": 8.0, "Metal Fragments": 100.0},
    "Metal Pipe": {"Scrap": 5.0, "High Quality Metal": 1.0},
    "Road Signs": {"Scrap": 5.0, "High Quality Metal": 1.0},
    "Rifle Body": {"Scrap": 25.0, "High Quality Metal": 2.0},
    "SMG Body": {"Scrap": 15.0, "High Quality Metal": 2.0},
    "Semi Automatic Body": {"Scrap": 15.0, "High Quality Metal": 2.0},
}

BUILDING_COSTS: dict[str, dict[str, int]] = {
    "Twig": {"Wood": 10},
    "Wood": {"Wood": 200},
    "Stone": {"Stone": 300},
    "Sheet Metal": {"Metal Fragments": 200},
    "Armored": {"High Quality Metal": 25},
}

GENE_WEIGHTS: dict[str, int] = {
    "G": 3,
    "Y": 3,
    "H": 1,
    "W": -2,
    "X": -3,
}
