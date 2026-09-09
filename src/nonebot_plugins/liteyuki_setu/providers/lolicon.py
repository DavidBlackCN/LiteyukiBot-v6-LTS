from __future__ import annotations

from typing import Any

from ..models import ImageQuery, ImageResult, NoResultError, ProviderCapabilities, ProviderError
from .base import ImageProvider


class LoliconProvider(ImageProvider):
    name = "lolicon"
    capabilities = ProviderCapabilities(random=True, count=True, keyword=True, tags=True, uid=True,
                                        size=True, exclude_ai=True, orientation=True, metadata=True,
                                        safe_classification=True, r18=True)

    def __init__(self, client: Any, api_url: str, pixiv_proxy: str):
        self.client = client
        self.api_url = api_url
        self.pixiv_proxy = pixiv_proxy

    async def fetch(self, query: ImageQuery) -> list[ImageResult]:
        # Both safe and approved private R18 requests explicitly select a grade.
        payload: dict[str, Any] = {"r18": 1 if query.r18 else 0, "num": query.count,
                                   "size": [query.size], "excludeAI": int(query.exclude_ai)}
        if self.pixiv_proxy:
            payload["proxy"] = self.pixiv_proxy
        if query.keyword:
            payload["keyword"] = query.keyword
        if query.tags:
            payload["tag"] = query.tags
        if query.uid:
            payload["uid"] = query.uid
        if query.orientation:
            payload["aspectRatio"] = "portrait" if query.orientation == "portrait" else "landscape"
        response = await self.client.request_json("POST", self.api_url, json=payload)
        if not isinstance(response, dict):
            raise ProviderError("Lolicon 返回格式无效")
        if response.get("error"):
            raise ProviderError("Lolicon 请求失败")
        data = response.get("data")
        if not isinstance(data, list):
            raise ProviderError("Lolicon 返回格式无效")
        results = [self._convert(item, query.size, query.r18) for item in data if isinstance(item, dict)]
        results = [item for item in results if item is not None]
        if not results:
            raise NoResultError("没有找到符合条件的图片。")
        return results[:query.count]

    def _convert(self, item: dict[str, Any], size: str, r18: bool) -> ImageResult | None:
        adult = item.get("r18")
        if r18:
            if adult is not True and adult != 1:
                return None
        elif adult is not False and adult != 0:
            return None
        urls = item.get("urls")
        if not isinstance(urls, dict):
            return None
        image_url = urls.get(size) or urls.get("regular") or urls.get("original")
        if not isinstance(image_url, str) or not image_url:
            return None
        pid = item.get("pid")
        return ImageResult(provider=self.name, image_url=image_url, pid=pid, uid=item.get("uid"),
                           title=item.get("title"), author=item.get("author"),
                           tags=[str(tag) for tag in item.get("tags", []) if str(tag)],
                           width=_int(item.get("width")), height=_int(item.get("height")),
                           ai_type=_int(item.get("aiType")), is_adult=r18,
                           source_url=f"https://www.pixiv.net/artworks/{pid}" if pid is not None else None)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None