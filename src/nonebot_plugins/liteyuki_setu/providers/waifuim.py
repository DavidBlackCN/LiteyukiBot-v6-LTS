from __future__ import annotations

import re
from typing import Any

from ..models import ImageQuery, ImageResult, NoResultError, ProviderCapabilities, ProviderError
from .base import ImageProvider


_PIXIV_ARTWORK = re.compile(r"pixiv\.net/(?:en/)?artworks/(\d+)", re.IGNORECASE)
_PIXIV_USER = re.compile(r"pixiv\.net/(?:en/)?users/(\d+)", re.IGNORECASE)


class WaifuImProvider(ImageProvider):
    name = "waifuim"
    rating_mode = "filterable"
    capabilities = ProviderCapabilities(
        random=True, count=True, keyword=True, tags=True, orientation=True,
        metadata=True, safe_classification=True, r18=True,
    )

    def __init__(self, client: Any, base_url: str, api_key: str = ""):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def fetch(self, query: ImageQuery) -> list[ImageResult]:
        params: list[tuple[str, Any]] = [
            ("IsNsfw", "True" if query.r18 else "False"),
            ("OrderBy", "Random"),
            ("PageSize", query.count),
        ]
        included_tags = [*query.tags]
        if query.keyword:
            included_tags.append(query.keyword)
        params.extend(("IncludedTags", tag) for tag in included_tags)
        if query.orientation:
            params.append(("Orientation", query.orientation.title()))
        headers = {"X-Api-Key": self.api_key} if self.api_key else None
        response = await self.client.request_json(
            "GET", f"{self.base_url}/images", params=params, headers=headers,
        )
        if not isinstance(response, dict):
            raise ProviderError("Waifu.im 返回格式无效")
        items = response.get("items")
        if not isinstance(items, list):
            raise ProviderError("Waifu.im 返回格式无效")
        results = [self._convert(item) for item in items if isinstance(item, dict)]
        converted = [item for item in results if item is not None]
        if not converted:
            raise NoResultError("没有找到符合条件的图片。")
        return converted[:query.count]

    def _convert(self, item: dict[str, Any]) -> ImageResult | None:
        image_url = item.get("url")
        if not isinstance(image_url, str) or not image_url:
            return None
        source_url = item.get("source") if isinstance(item.get("source"), str) else None
        artwork_match = _PIXIV_ARTWORK.search(source_url or "")
        artists = item.get("artists")
        artist = next((value for value in artists or [] if isinstance(value, dict)), {})
        user_match = _PIXIV_USER.search(str(artist.get("pixiv") or ""))
        tags = item.get("tags")
        return ImageResult(
            provider=self.name, image_url=image_url,
            pid=artwork_match.group(1) if artwork_match else item.get("id"),
            uid=user_match.group(1) if user_match else None,
            author=artist.get("name") if isinstance(artist.get("name"), str) else None,
            tags=[
                str(tag.get("slug") or tag.get("name")) for tag in tags or []
                if isinstance(tag, dict) and (tag.get("slug") or tag.get("name"))
            ],
            width=_int(item.get("width")), height=_int(item.get("height")),
            is_adult=item.get("isNsfw") if isinstance(item.get("isNsfw"), bool) else None,
            source_url=source_url,
        )


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
