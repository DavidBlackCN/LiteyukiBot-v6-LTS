from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from ..models import ImageQuery, ImageResult, NoResultError, ProviderCapabilities, ProviderError
from .base import ImageProvider


class RandomMageProvider(ImageProvider):
    name = "random_mage"
    rating_mode = "filterable"
    capabilities = ProviderCapabilities(
        random=True, count=True, tags=True, uid=True, pid=True, exclude_ai=True,
        orientation=True, metadata=True, safe_classification=True, r18=True,
    )

    def __init__(self, client: Any, base_url: str, api_key: str = ""):
        self.client = client
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key

    def supports(self, query: ImageQuery) -> bool:
        return super().supports(query) and len(query.uid) <= 1 and len(query.pid) <= 1

    async def fetch(self, query: ImageQuery) -> list[ImageResult]:
        params: list[tuple[str, Any]] = [
            ("limit", query.count),
            ("r18", 1 if query.r18 else 0),
            ("r18_strict", 1),
            ("ai_type", "0" if query.exclude_ai else "any"),
        ]
        params.extend(("included_tags", tag) for tag in query.tags)
        if query.uid:
            params.append(("user_id", query.uid[0]))
        if query.pid:
            params.append(("illust_id", query.pid[0]))
        if query.orientation:
            params.append(("orientation", query.orientation))
        headers = {"X-API-Key": self.api_key} if self.api_key else None
        response = await self.client.request_json(
            "GET", urljoin(self.base_url, "feed"), params=params, headers=headers,
        )
        if not isinstance(response, dict):
            raise ProviderError("Random Mage 返回格式无效")
        if response.get("ok") is not True:
            raise ProviderError(str(response.get("message") or response.get("code") or "Random Mage 请求失败"))
        data = response.get("data")
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ProviderError("Random Mage 返回格式无效")
        results = [self._convert(item, query) for item in items if isinstance(item, dict)]
        converted = [item for item in results if item is not None]
        if not converted:
            raise NoResultError("没有找到符合条件的图片。")
        return converted[:query.count]

    def _convert(self, item: dict[str, Any], query: ImageQuery) -> ImageResult | None:
        image = item.get("image")
        urls = item.get("urls")
        if not isinstance(image, dict) or not isinstance(urls, dict):
            return None
        image_urls = list(dict.fromkeys(
            urljoin(self.base_url, value)
            for key in ("proxy", "local", "origin")
            if isinstance((value := urls.get(key)), str) and value
        ))
        if not image_urls:
            return None
        user = image.get("user") if isinstance(image.get("user"), dict) else {}
        pid = image.get("illust_id")
        tags = item.get("tags")
        return ImageResult(
            provider=self.name, image_url=image_urls[0],
            fallback_image_urls=image_urls[1:], pid=pid, uid=user.get("id"),
            title=image.get("title"), author=user.get("name"),
            tags=[str(tag) for tag in tags or [] if str(tag)],
            width=_int(image.get("width")), height=_int(image.get("height")),
            ai_type=_int(image.get("ai_type")), is_adult=query.r18,
            source_url=f"https://www.pixiv.net/artworks/{pid}" if pid is not None else None,
        )


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
