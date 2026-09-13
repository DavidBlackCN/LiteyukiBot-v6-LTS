from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from ..models import ImageQuery, ImageResult, NoResultError, ProviderCapabilities, ProviderError
from .base import ImageProvider


class _RateLimiter:
    def __init__(self, limit: int, period: float):
        self.limit = limit
        self.period = period
        self.timestamps: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            now = time.monotonic()
            while self.timestamps and now - self.timestamps[0] >= self.period:
                self.timestamps.popleft()
            if len(self.timestamps) >= self.limit:
                await asyncio.sleep(self.period - (now - self.timestamps[0]))
                now = time.monotonic()
                while self.timestamps and now - self.timestamps[0] >= self.period:
                    self.timestamps.popleft()
            self.timestamps.append(time.monotonic())


_rate_limiter = _RateLimiter(3, 5.0)


class LieMoeProvider(ImageProvider):
    name = "liemoe"
    rating_mode = "sfw_only"
    capabilities = ProviderCapabilities(
        random=True, count=True, size=True, orientation=True, safe_classification=True,
    )

    def __init__(self, client: Any, base_url: str):
        self.client = client
        self.base_url = base_url.rstrip("/")

    async def fetch(self, query: ImageQuery) -> list[ImageResult]:
        await _rate_limiter.wait()
        sort = {"portrait": "mp", "landscape": "pc"}.get(query.orientation, "approve")
        params: dict[str, Any] = {"sort": sort, "type": "json", "num": query.count}
        thumbnail = {
            "small": "large", "thumb": "medium", "mini": "small",
        }.get(query.size)
        if thumbnail:
            params["thumbnail"] = thumbnail
        response = await self.client.request_json(
            "GET", f"{self.base_url}/random", params=params,
        )
        if not isinstance(response, dict):
            raise ProviderError("LieMoe 返回格式无效")
        values = response.get("pic")
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            raise ProviderError("LieMoe 返回格式无效")
        results = [
            ImageResult(provider=self.name, image_url=value, is_adult=False)
            for value in values if isinstance(value, str) and value.startswith(("http://", "https://"))
        ]
        if not results:
            raise NoResultError("没有找到符合条件的图片。")
        return results[:query.count]
