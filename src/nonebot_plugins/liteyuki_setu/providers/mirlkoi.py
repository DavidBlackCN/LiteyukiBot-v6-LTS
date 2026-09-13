from __future__ import annotations

from typing import Any

from ..models import ImageQuery, ImageResult, NoResultError, ProviderCapabilities, ProviderError
from .base import ImageProvider


class MirlKoiProvider(ImageProvider):
    name = "mirlkoi"
    rating_mode = "bucketed"
    capabilities = ProviderCapabilities(random=True, count=True, size=True,
                                        safe_classification=True, r18=True)

    def __init__(self, client: Any, base_url: str, endpoint: str,
                 sfw_sort: str = "CDNcat", r18_sort: str = "CDNsetu",
                 random_sort: str = "CDNiw233", portrait_sort: str = "CDNmp",
                 landscape_sort: str = "CDNpc"):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint.strip() or "/api.php"
        self.sfw_sort = sfw_sort
        self.r18_sort = r18_sort
        # Retained as explicit configuration for deployments which use these
        # categories directly; classified requests must not silently use them.
        self.random_sort = random_sort
        self.portrait_sort = portrait_sort
        self.landscape_sort = landscape_sort

    def supports(self, query: ImageQuery) -> bool:
        return (super().supports(query) and query.size in {"regular", "original"}
                and not query.orientation)

    async def fetch(self, query: ImageQuery) -> list[ImageResult]:
        if query.orientation:
            raise ProviderError("MirlKoi 当前无法同时保证内容分级和横竖筛选")
        sort = self.r18_sort if query.r18 else self.sfw_sort
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
            ImageResult(provider=self.name, image_url=self._size_url(item, query.size),
                        is_adult=query.r18)
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
