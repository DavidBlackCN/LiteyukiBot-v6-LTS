"""Liteyuki card rendering for normalized Bilibili events."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from typing import Any

from src.utils.base.resource import get_path
from src.utils.message.html_tool import template2image_element

from .models import BilibiliEvent


_TEMPLATE_BY_KIND = {
    "video": "templates/bilibili_video.html",
    "dynamic": "templates/bilibili_dynamic.html",
    "live_start": "templates/bilibili_live.html",
    "live_end": "templates/bilibili_live.html",
}
_LABELS = {
    "video": "视频",
    "dynamic": "动态",
    "live_start": "直播",
    "live_end": "直播",
}
_METRIC_LABELS = {"view": "播放", "like": "点赞", "reply": "评论", "coin": "投币", "area": "分区"}
BILIBILI_IMAGE_DOWNLOAD_CONCURRENCY = 2
_image_download_semaphore = asyncio.Semaphore(BILIBILI_IMAGE_DOWNLOAD_CONCURRENCY)


def _body_preview(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…\n（正文较长，完整内容请查看原链接）"


def event_view(event: BilibiliEvent, body_limit: int = 600) -> dict[str, Any]:
    return {
        "label": "转发动态" if event.original else "直播动态" if event.live else "专栏" if event.display_type == "article" else _LABELS[event.kind],
        "state": "开播" if event.kind == "live_start" else "下播" if event.kind == "live_end" else event.live.state if event.live else "",
        "author": event.author_name or f"UP {event.uid}",
        "title": "转发动态" if event.original else event.title or "Bilibili 更新",
        "body": _body_preview(event.body, body_limit),
        "url": event.url,
        "timestamp": _format_time(event.timestamp),
        "avatar": "",
        "covers": [],
        "display_type": "forward" if event.original else "live" if event.live or event.kind.startswith("live_") else "video" if event.kind == "video" else event.display_type,
        "live_url": event.live.url if event.live else "",
        "original": {
            **event.original.model_dump(exclude={"cover_urls", "live"}),
            "body": _body_preview(event.original.body, body_limit),
            "covers": [],
            "live": event.original.live.model_dump() if event.original.live else None,
        } if event.original else None,
        "metrics": [
            {"label": _METRIC_LABELS.get(key, key), "value": str(value)}
            for key, value in {**({"area": event.live.area_name} if event.live else {}), **event.metrics}.items()
            if value not in {None, ""}
        ][:4],
    }


async def render_event_card(event: BilibiliEvent, client, scale_factor: float = 1.5) -> bytes:
    template = get_path(_TEMPLATE_BY_KIND["live_start" if event.live and not event.original else event.kind], abs_path=True)
    if not template:
        raise FileNotFoundError("Bilibili 卡片资源尚未加载，请执行 rpm reload")
    from . import config

    view = event_view(event, config.bilibili_card_body_limit)
    cover_urls = [
        url for url in event.cover_urls
        if not event.original or url not in event.original.cover_urls
    ]
    original_urls = event.original.cover_urls if event.original else []
    urls = list(dict.fromkeys(url for url in [event.avatar_url, *cover_urls, *original_urls] if url))
    images = await asyncio.gather(*(_data_uri(client, url) for url in urls), return_exceptions=True)
    embedded = {url: image for url, image in zip(urls, images) if isinstance(image, str)}
    view["avatar"] = embedded.get(event.avatar_url, "")
    view["covers"] = [embedded[url] for url in cover_urls if url in embedded]
    if view["original"] is not None:
        view["original"]["covers"] = [embedded[url] for url in original_urls if url in embedded]
    return await template2image_element(
        template,
        {"data": view},
        "body",
        wait_for="window.bilibiliCardReady === true",
        wait_timeout=5000,
        scale_factor=scale_factor,
    )


async def _data_uri(client, url: str) -> str:
    async with _image_download_semaphore:
        image = await client.download_image(url)
    encoded = base64.b64encode(image.data).decode("ascii")
    return f"data:{image.content_type};base64,{encoded}"


def _format_time(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone().strftime("%Y-%m-%d %H:%M")
