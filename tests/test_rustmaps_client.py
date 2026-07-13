from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rust_companion_plus.services.http_client import ApiHttpError
from rust_companion_plus.services.rustmaps_client import RustMapsClient


MAP_PAYLOAD = {
    "data": {
        "id": "map-1",
        "type": "procedural",
        "seed": 1234,
        "size": 4500,
        "saveVersion": 2600,
        "url": "https://rustmaps.com/map-1",
        "rawImageUrl": "https://cdn/raw.png",
        "imageUrl": "https://cdn/map.png",
        "imageIconUrl": "https://cdn/icons.png",
        "thumbnailUrl": "https://cdn/thumb.png",
        "canDownload": True,
        "downloadUrl": "https://cdn/world.map",
        "totalMonuments": 12,
        "monuments": [{"type": "airfield", "coordinates": {"x": 1, "y": 2}}],
        "landPercentageOfMap": 61,
        "biomePercentages": {"s": 10.0, "d": 20.0, "f": 70.0},
        "islands": 3,
        "mountains": 5,
    }
}


class RustMapsClientTests(unittest.TestCase):
    def test_status_payload(self) -> None:
        client = RustMapsClient("secret", request=lambda *args, **kwargs: MAP_PAYLOAD)
        metadata = client.get_map(4500, 1234)
        self.assertEqual(metadata.map_id, "map-1")
        self.assertEqual(metadata.total_monuments, 12)
        self.assertTrue(metadata.can_download)

    def test_missing_map_can_be_queued(self) -> None:
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs.get("payload")))
            if method == "GET":
                raise ApiHttpError(404, "not found")
            return {"data": {"mapId": "queued", "state": "queued"}}

        client = RustMapsClient("secret", request=fake_request)
        self.assertIsNone(client.ensure_map(4500, 1234, auto_generate=True))
        self.assertEqual(calls[-1][0], "POST")
        self.assertEqual(calls[-1][2]["seed"], "1234")

    def test_assets_use_icon_map_and_optional_map_file(self) -> None:
        downloaded = []

        def fake_download(url, destination, **kwargs):
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
            downloaded.append((url, path.name))
            return path

        client = RustMapsClient("secret", request=lambda *args, **kwargs: MAP_PAYLOAD, downloader=fake_download)
        metadata = client.get_map(4500, 1234)
        with tempfile.TemporaryDirectory() as temp:
            assets = client.download_assets(metadata, temp, include_map_file=True)
            self.assertTrue(assets.map_image.exists())
            self.assertTrue(assets.map_file.exists())
        self.assertIn(("https://cdn/icons.png", "map_texture.png"), downloaded)


if __name__ == "__main__":
    unittest.main()
