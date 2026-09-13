from __future__ import annotations

import asyncio
from typing import Any

from ..models import (ImageQuery, ImageResult, NetworkError, NoResultError,
                      ProviderCapabilities, ProviderError)
from .base import ImageProvider


class DuckMoXProvider(ImageProvider):
    name = "duckmo_x"
    rating_mode = "unclassified"
    capabilities = ProviderCapabilities(random=True, count=True, metadata=True)

    def __init__(self, client: Any, url: str,
                 render_url: str = "https://rand-x.mossia.top/"):
        self.client = client
        self.url = url.rstrip("/")
        self.render_url = render_url
        self._semaphore = asyncio.Semaphore(2)

    async def fetch(self, query: ImageQuery) -> list[ImageResult]:
        async def fetch_one() -> ImageResult | None:
            try:
                async with self._semaphore:
                    response = await self.client.request_json("GET", self.url)
            except NetworkError:
                return ImageResult(provider=self.name, image_url=self.render_url)
            if not isinstance(response, dict):
                raise ProviderError("DuckMo X 返回格式无效")
            if response.get("success") is not True:
                raise ProviderError(str(response.get("message") or "DuckMo X 请求失败"))
            data = response.get("data")
            if not isinstance(data, list) or not data or not isinstance(data[0], dict):
                return None
            item = data[0]
            image_url = item.get("pictureUrl")
            if not isinstance(image_url, str) or not image_url:
                return None
            return ImageResult(
                provider=self.name, image_url=image_url,
                fallback_image_urls=[self.render_url],
                source_url=item.get("url") if isinstance(item.get("url"), str) else None,
            )

        results = await asyncio.gather(*(fetch_one() for _ in range(query.count)))
        converted = [item for item in results if item is not None]
        if not converted:
            raise NoResultError("没有找到符合条件的图片。")
        return converted[:query.count]
