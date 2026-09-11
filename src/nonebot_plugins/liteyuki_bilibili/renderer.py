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
    "video": "BILIBILI · VIDEO",
    "dynamic": "BILIBILI · DYNAMIC",
    "live_start": "BILIBILI · LIVE START",
    "live_end": "BILIBILI · LIVE END",
}
_METRIC_LABELS = {"view": "播放", "like": "点赞", "reply": "评论", "coin": "投币", "area": "分区"}


def event_view(event: BilibiliEvent) -> dict[str, Any]:
    return {
        "label": _LABELS[event.kind],
        "state": "开播" if event.kind == "live_start" else "下播" if event.kind == "live_end" else "",
        "author": event.author_name or f"UP {event.uid}",
        "title": event.title or "Bilibili 更新",
        "body": event.body[:1600],
        "url": event.url,
        "timestamp": _format_time(event.timestamp),
        "avatar": "",
        "covers": [],
        "metrics": [
            {"label": _METRIC_LABELS.get(key, key), "value": str(value)}
            for key, value in event.metrics.items()
            if value not in {None, ""}
        ][:4],
    }


async def render_event_card(event: BilibiliEvent, client, scale_factor: float = 1.5) -> bytes:
    template = get_path(_TEMPLATE_BY_KIND[event.kind], abs_path=True)
    if not template:
        raise FileNotFoundError("Bilibili 卡片资源尚未加载，请执行 rpm reload")
    view = event_view(event)
    urls = [event.avatar_url, *event.cover_urls[:4]]
    images = await asyncio.gather(
        *(_data_uri(client, url) for url in urls if url), return_exceptions=True
    )
    avatar_offset = 1 if event.avatar_url else 0
    if event.avatar_url and images and isinstance(images[0], str):
        view["avatar"] = images[0]
    view["covers"] = [image for image in images[avatar_offset:] if isinstance(image, str)]
    return await template2image_element(
        template,
        {"data": view},
        "body",
        wait_for="window.bilibiliCardReady === true",
        wait_timeout=5000,
        scale_factor=scale_factor,
    )


async def _data_uri(client, url: str) -> str:
    image = await client.download_image(url)
    encoded = base64.b64encode(image.data).decode("ascii")
    return f"data:{image.content_type};base64,{encoded}"


def _format_time(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone().strftime("%Y-%m-%d %H:%M")
