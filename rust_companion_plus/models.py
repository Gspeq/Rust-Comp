from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class RustCredentials:
    host: str = ""
    port: int = 0
    steam_id: int = 0
    player_token: int = 0

    def is_complete(self) -> bool:
        return bool(self.host and self.port and self.steam_id and self.player_token)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RustCredentials":
        data = data or {}
        return cls(
            host=str(data.get("host", "")),
            port=int(data.get("port", 0) or 0),
            steam_id=int(data.get("steam_id", 0) or 0),
            player_token=int(data.get("player_token", 0) or 0),
        )


@dataclass(slots=True)
class SetupComponent:
    component: str
    quantity: int = 1
    state: str = "Planned"
    zone: str = "Main"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SetupComponent":
        return cls(
            component=str(data["component"]),
            quantity=max(0, int(data.get("quantity", 1))),
            state=str(data.get("state", "Planned")),
            zone=str(data.get("zone", "Main")),
            note=str(data.get("note", "")),
        )


@dataclass(slots=True)
class ElectricalSetup:
    name: str = "Main Base"
    version: int = 1
    goal_text: str = ""
    components: list[SetupComponent] = field(default_factory=list)
    assumptions: dict[str, float] = field(
        default_factory=lambda: {
            "solar_utilization": 0.35,
            "wind_utilization": 0.55,
            "battery_charge_fraction": 1.0,
        }
    )
    notes: str = ""
    setup_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["components"] = [item.to_dict() for item in self.components]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElectricalSetup":
        return cls(
            name=str(data.get("name", "Main Base")),
            version=int(data.get("version", 1)),
            goal_text=str(data.get("goal_text", "")),
            components=[
                SetupComponent.from_dict(item)
                for item in data.get("components", [])
            ],
            assumptions={
                "solar_utilization": float(
                    data.get("assumptions", {}).get("solar_utilization", 0.35)
                ),
                "wind_utilization": float(
                    data.get("assumptions", {}).get("wind_utilization", 0.55)
                ),
                "battery_charge_fraction": float(
                    data.get("assumptions", {}).get("battery_charge_fraction", 1.0)
                ),
            },
            notes=str(data.get("notes", "")),
            setup_id=str(data.get("setup_id", uuid4())),
            created_at=str(data.get("created_at", utc_now_iso())),
            updated_at=str(data.get("updated_at", utc_now_iso())),
        )


@dataclass(slots=True)
class ThreatEntry:
    attacker: str
    victim: str
    weapon: str = ""
    grid: str = ""
    occurred_at: str = field(default_factory=utc_now_iso)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ResourceOverlay:
    resource: str
    x_fraction: float
    y_fraction: float
    intensity: int = 1
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
