from __future__ import annotations

from typing import Any

from ..models import ImageQuery, ImageResult, NoResultError, ProviderCapabilities, ProviderError
from .base import ImageProvider


class MirlKoiProvider(ImageProvider):
    name = "mirlkoi"
    # api.cnmiw.com documents CDNiw233 as its no-setu CDN category. It supports
    # random batches and horizontal/vertical variants, not Pixiv metadata filters.
    capabilities = ProviderCapabilities(random=True, count=True, size=True, orientation=True)

    def __init__(self, client: Any, base_url: str, endpoint: str):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint.strip() or "/api.php"

    def supports(self, query: ImageQuery) -> bool:
        return super().supports(query) and query.size in {"regular", "original"}

    async def fetch(self, query: ImageQuery) -> list[ImageResult]:
        sort = {"portrait": "CDNmp", "landscape": "CDNpc"}.get(query.orientation, "CDNiw233")
        url = f"{self.base_url}/{self.endpoint.lstrip('/')}"
        response = await self.client.request_json(
            "GET", url, params={"sort": sort, "type": "json", "num": query.count},
        )
        if isinstance(response, dict):
            values = response.get("pic") or response.get("url") or response.get("img") or []
        elif isinstance(response, list):
            values = response
        else:
            values = []
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            raise ProviderError("MirlKoi 返回格式无效")
        results = [
            ImageResult(provider=self.name, image_url=self._size_url(item, query.size))
            for item in values if isinstance(item, str) and item.startswith(("http://", "https://"))
        ]
        if not results:
            raise NoResultError("没有找到符合条件的图片。")
        return results[:query.count]

    @staticmethod
    def _size_url(url: str, size: str) -> str:
        if size == "regular":
            return url.replace("/large/", "/bmiddle/")
        return url