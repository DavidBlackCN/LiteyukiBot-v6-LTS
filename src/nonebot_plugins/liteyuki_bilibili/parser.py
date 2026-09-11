"""Bilibili-only link extraction and normalized parser service."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .models import BilibiliEvent, BilibiliLiveStatus, BilibiliVideo


_BV = re.compile(r"(?<![A-Za-z0-9])(?P<bvid>BV[1-9A-HJ-NP-Za-km-z]{10})(?![A-Za-z0-9])", re.I)
_AV = re.compile(r"(?<![A-Za-z0-9])av(?P<aid>\d+)(?![A-Za-z0-9])", re.I)
_URL = re.compile(r"https?://[^\s<>]+", re.I)
_TRAILING_PUNCTUATION = ".,!?;:，。！？；：)]}>\"'”’"


@dataclass(frozen=True)
class BilibiliLink:
    kind: str
    identifier: str
    url: str


def extract_links(text: str) -> list[BilibiliLink]:
    """Extract direct Bilibili targets without doing network I/O."""
    links: list[BilibiliLink] = []
    url_matches = list(_URL.finditer(text))

    def inside_url(position: int) -> bool:
        return any(match.start() <= position < match.end() for match in url_matches)

    for match in _BV.finditer(text):
        if inside_url(match.start()):
            continue
        bvid = match.group("bvid")
        links.append(BilibiliLink("video", bvid, f"https://www.bilibili.com/video/{bvid}"))
    for match in _AV.finditer(text):
        if inside_url(match.start()):
            continue
        aid = match.group("aid")
        links.append(BilibiliLink("video", f"av{aid}", f"https://www.bilibili.com/video/av{aid}"))
    for match in url_matches:
        link = _link_from_url(match.group(0).rstrip(_TRAILING_PUNCTUATION))
        if link is not None:
            links.append(link)
    return _deduplicate(links)


async def resolve_links(text: str, client) -> list[BilibiliLink]:
    """Resolve only b23.tv redirects and preserve per-message de-duplication."""
    links = extract_links(text)
    resolved: list[BilibiliLink] = []
    for link in links:
        if link.kind != "short":
            resolved.append(link)
            continue
        url = await client.resolve_short_url(link.url)
        target = _link_from_url(url)
        if target is not None and target.kind != "short":
            resolved.append(target)
    return _deduplicate(resolved)


class BilibiliLinkParser:
    """Turn a recognized target into the shared card event model."""

    def __init__(self, client) -> None:
        self.client = client

    async def parse(self, link: BilibiliLink) -> BilibiliEvent:
        if link.kind == "video":
            video = await self.client.get_video_info(
                bvid=link.identifier if link.identifier.upper().startswith("BV") else "",
                aid=link.identifier[2:] if link.identifier.lower().startswith("av") else "",
            )
            return _video_event(video)
        if link.kind == "dynamic":
            return await self.client.get_dynamic_detail(link.identifier)
        if link.kind == "live":
            status = await self.client.get_live_room_status(link.identifier)
            return _live_event(status)
        raise ValueError(f"Unsupported Bilibili link kind: {link.kind}")


def _link_from_url(url: str) -> BilibiliLink | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if host in {"b23.tv", "www.b23.tv"}:
        return BilibiliLink("short", url, url)
    if host in {"www.bilibili.com", "bilibili.com", "m.bilibili.com"}:
        video = _BV.search(path)
        if video:
            bvid = video.group("bvid")
            return BilibiliLink("video", bvid, f"https://www.bilibili.com/video/{bvid}")
        video = _AV.search(path)
        if video:
            aid = video.group("aid")
            return BilibiliLink("video", f"av{aid}", f"https://www.bilibili.com/video/av{aid}")
        opus = re.fullmatch(r"/(?:opus|dynamic)/(\d+)", path)
        if opus:
            dynamic_id = opus.group(1)
            return BilibiliLink("dynamic", dynamic_id, f"https://t.bilibili.com/{dynamic_id}")
    if host == "t.bilibili.com":
        dynamic = re.fullmatch(r"/(\d+)", path)
        if dynamic:
            dynamic_id = dynamic.group(1)
            return BilibiliLink("dynamic", dynamic_id, f"https://t.bilibili.com/{dynamic_id}")
    if host == "live.bilibili.com":
        room = re.fullmatch(r"/(\d+)", path)
        if room:
            room_id = room.group(1)
            return BilibiliLink("live", room_id, f"https://live.bilibili.com/{room_id}")
    return None


def _deduplicate(links: list[BilibiliLink]) -> list[BilibiliLink]:
    unique: list[BilibiliLink] = []
    seen: set[tuple[str, str]] = set()
    for link in links:
        key = (link.kind, link.identifier.lower())
        if key not in seen:
            seen.add(key)
            unique.append(link)
    return unique


def _video_event(video: BilibiliVideo) -> BilibiliEvent:
    event_id = video.bvid or video.aid
    return BilibiliEvent(
        kind="video",
        uid=video.author_uid,
        event_id=event_id,
        title=video.title,
        body=video.description,
        url=video.url,
        author_name=video.author_name,
        avatar_url=video.avatar_url,
        cover_urls=[video.cover_url] if video.cover_url else [],
        timestamp=video.timestamp,
        metrics=video.metrics,
    )


def _live_event(status: BilibiliLiveStatus) -> BilibiliEvent:
    return BilibiliEvent(
        kind="live_start" if status.live else "live_end",
        uid=status.uid,
        event_id=f"{status.room_id}:{'live' if status.live else 'offline'}",
        title=status.title or ("正在直播" if status.live else "当前未开播"),
        url=status.url,
        cover_urls=[status.cover_url] if status.cover_url else [],
        metrics={"area": status.area_name},
    )
