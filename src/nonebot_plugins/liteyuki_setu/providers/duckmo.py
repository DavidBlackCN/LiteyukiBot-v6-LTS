from __future__ import annotations

from typing import Any

from ..models import ImageQuery, ImageResult, NoResultError, ProviderCapabilities, ProviderError
from .base import ImageProvider


class DuckMoProvider(ImageProvider):
    name = "duckmo"
    rating_mode = "filterable"
    capabilities = ProviderCapabilities(
        random=True, count=True, uid=True, pid=True, author=True, size=True,
        exclude_ai=True, orientation=True, metadata=True,
        safe_classification=True, r18=True,
    )

    def __init__(self, client: Any, base_url: str):
        self.client = client
        self.base_url = base_url.rstrip("/")

    async def fetch(self, query: ImageQuery) -> list[ImageResult]:
        payload: dict[str, Any] = {
            "num": query.count,
            "r18Type": 1 if query.r18 else 0,
            "sizeList": [query.size],
        }
        if query.exclude_ai:
            payload["aiType"] = 1
        if query.pid:
            payload["pid"] = query.pid
        if query.uid:
            payload["uid"] = query.uid
        if query.author:
            payload["author"] = query.author
        if query.orientation:
            payload["imageSizeType"] = 2 if query.orientation == "portrait" else 1

        response = await self.client.request_json("POST", self.base_url, json=payload)
        if not isinstance(response, dict):
            raise ProviderError("DuckMo 返回格式无效")
        if response.get("success") is not True:
            raise ProviderError(str(response.get("message") or "DuckMo 请求失败"))
        data = response.get("data")
        if not isinstance(data, list):
            raise ProviderError("DuckMo 返回格式无效")
        results = [self._convert(item, query) for item in data if isinstance(item, dict)]
        converted = [item for item in results if item is not None]
        if not converted:
            raise NoResultError("没有找到符合条件的图片。")
        return converted[:query.count]

    def _convert(self, item: dict[str, Any], query: ImageQuery) -> ImageResult | None:
        urls = item.get("urlsList")
        if not isinstance(urls, list):
            return None
        available = {
            str(value.get("urlSize")): value.get("url")
            for value in urls if isinstance(value, dict) and isinstance(value.get("url"), str)
        }
        image_url = (available.get(query.size) or available.get("regular")
                     or available.get("original") or next(iter(available.values()), None))
        if not image_url:
            return None
        tags = item.get("tagsList")
        tag_names = [
            str(tag.get("tagName")) for tag in tags or []
            if isinstance(tag, dict) and tag.get("tagName")
        ]
        pid = item.get("pid")
        return ImageResult(
            provider=self.name, image_url=image_url, pid=pid, uid=item.get("uid"),
            title=item.get("title"), author=item.get("author"), tags=tag_names,
            width=_int(item.get("width")), height=_int(item.get("height")),
            ai_type=_int(item.get("aiType")), is_adult=query.r18,
            source_url=f"https://www.pixiv.net/artworks/{pid}" if pid is not None else None,
        )


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
