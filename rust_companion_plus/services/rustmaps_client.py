from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from rust_companion_plus.services.http_client import ApiHttpError, download_file, request_json


RUSTMAPS_API = "https://api.rustmaps.com/v4"


@dataclass(slots=True)
class RustMapMetadata:
    map_id: str
    map_type: str
    seed: int
    size: int
    save_version: int
    page_url: str
    raw_image_url: str
    image_url: str
    image_icon_url: str
    thumbnail_url: str
    can_download: bool
    download_url: str
    total_monuments: int
    monuments: list[dict[str, Any]] = field(default_factory=list)
    land_percentage: int = 0
    biome_percentages: dict[str, float] = field(default_factory=dict)
    islands: int = 0
    mountains: int = 0
    rivers: int = 0
    lakes: int = 0
    canyons: int = 0
    oases: int = 0
    buildable_rocks: int = 0
    state: str = "complete"
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RustMapMetadata":
        data = payload.get("data") or payload
        return cls(
            map_id=str(data.get("id") or data.get("mapId") or ""),
            map_type=str(data.get("type") or "procedural"),
            seed=int(data.get("seed") or 0),
            size=int(data.get("size") or 0),
            save_version=int(data.get("saveVersion") or 0),
            page_url=str(data.get("url") or ""),
            raw_image_url=str(data.get("rawImageUrl") or ""),
            image_url=str(data.get("imageUrl") or ""),
            image_icon_url=str(data.get("imageIconUrl") or ""),
            thumbnail_url=str(data.get("thumbnailUrl") or ""),
            can_download=bool(data.get("canDownload")),
            download_url=str(data.get("downloadUrl") or ""),
            total_monuments=int(data.get("totalMonuments") or len(data.get("monuments") or [])),
            monuments=list(data.get("monuments") or []),
            land_percentage=int(data.get("landPercentageOfMap") or 0),
            biome_percentages=dict(data.get("biomePercentages") or {}),
            islands=int(data.get("islands") or 0),
            mountains=int(data.get("mountains") or 0),
            rivers=int(data.get("rivers") or 0),
            lakes=int(data.get("lakes") or 0),
            canyons=int(data.get("canyons") or 0),
            oases=int(data.get("oases") or 0),
            buildable_rocks=int(data.get("buildableRocks") or 0),
            state=str(data.get("state") or "complete"),
            raw=data,
        )


@dataclass(slots=True)
class RustMapsAssets:
    folder: Path
    map_image: Path | None = None
    raw_image: Path | None = None
    map_file: Path | None = None


class RustMapsClient:
    def __init__(
        self,
        api_key: str = "",
        *,
        request: Callable[..., dict[str, Any]] = request_json,
        downloader: Callable[..., Path] = download_file,
        api_url: str = RUSTMAPS_API,
    ) -> None:
        self.api_key = api_key.strip()
        self.request = request
        self.downloader = downloader
        self.api_url = api_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("Add a RustMaps API key from the RustMaps dashboard first.")
        return {"X-API-Key": self.api_key, "Accept": "application/json"}

    def get_map(self, size: int, seed: int) -> RustMapMetadata:
        payload = self.request(
            "GET",
            f"{self.api_url}/maps/{int(size)}/{int(seed)}",
            headers=self._headers(),
        )
        return RustMapMetadata.from_payload(payload)

    def generate_procedural(self, size: int, seed: int, *, staging: bool = False) -> dict[str, Any]:
        return self.request(
            "POST",
            f"{self.api_url}/maps",
            headers=self._headers(),
            payload={"size": int(size), "seed": str(int(seed)), "staging": bool(staging)},
        )

    def ensure_map(self, size: int, seed: int, *, auto_generate: bool = False) -> RustMapMetadata | None:
        try:
            return self.get_map(size, seed)
        except ApiHttpError as exc:
            if exc.status == 404 and auto_generate:
                self.generate_procedural(size, seed)
                return None
            if exc.status == 409:
                return None
            raise

    def download_assets(
        self,
        metadata: RustMapMetadata,
        folder: str | Path,
        *,
        include_map_file: bool = False,
    ) -> RustMapsAssets:
        root = Path(folder).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        result = RustMapsAssets(root)

        image_source = metadata.image_icon_url or metadata.image_url or metadata.raw_image_url
        if image_source:
            result.map_image = self.downloader(
                image_source,
                root / "map_texture.png",
                headers=headers,
                max_bytes=80 * 1024 * 1024,
            )
        if metadata.raw_image_url and metadata.raw_image_url != image_source:
            result.raw_image = self.downloader(
                metadata.raw_image_url,
                root / "raw_map.png",
                headers=headers,
                max_bytes=80 * 1024 * 1024,
            )
        if include_map_file and metadata.can_download and metadata.download_url:
            result.map_file = self.downloader(
                metadata.download_url,
                root / f"{metadata.size}_{metadata.seed}.map",
                headers=headers,
                max_bytes=512 * 1024 * 1024,
            )
        return result

    @staticmethod
    def open_image(path: str | Path) -> Image.Image:
        with Image.open(path) as image:
            return image.convert("RGBA").copy()
