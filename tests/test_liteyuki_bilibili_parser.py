import asyncio

from src.nonebot_plugins.liteyuki_bilibili.models import BilibiliLiveStatus, BilibiliVideo
from src.nonebot_plugins.liteyuki_bilibili.parser import (
    BilibiliLink,
    BilibiliLinkParser,
    extract_links,
    resolve_links,
)


def test_extracts_bv_av_video_dynamic_opus_and_live_once_per_target() -> None:
    text = """
    BV1xx411c7mD av170001 https://www.bilibili.com/video/BV1xx411c7mD
    https://t.bilibili.com/123 https://www.bilibili.com/opus/123
    https://live.bilibili.com/456
    """
    links = extract_links(text)

    assert [(link.kind, link.identifier) for link in links] == [
        ("video", "BV1xx411c7mD"),
        ("video", "av170001"),
        ("dynamic", "123"),
        ("live", "456"),
    ]


def test_short_link_only_accepts_client_resolved_bilibili_target() -> None:
    class Client:
        async def resolve_short_url(self, url: str) -> str:
            assert url == "https://b23.tv/test"
            return "https://www.bilibili.com/video/BV1xx411c7mD"

    links = asyncio.run(resolve_links("分享 https://b23.tv/test", Client()))
    assert links == [BilibiliLink("video", "BV1xx411c7mD", "https://www.bilibili.com/video/BV1xx411c7mD")]


def test_non_bilibili_url_does_not_trigger() -> None:
    assert extract_links("https://example.invalid/video/BV1xx411c7mD") == []


def test_parser_normalizes_video_and_live_events() -> None:
    class Client:
        async def get_video_info(self, **_kwargs):
            return BilibiliVideo(
                bvid="BV1xx411c7mD",
                author_uid="42",
                author_name="UP",
                title="视频",
                cover_url="https://i0.hdslb.com/video-cover.jpg",
            )

        async def get_live_room_status(self, room_id: str):
            return BilibiliLiveStatus(uid="42", room_id=room_id, live=True, title="直播")

    parser = BilibiliLinkParser(Client())
    video = asyncio.run(parser.parse(BilibiliLink("video", "BV1xx411c7mD", "")))
    live = asyncio.run(parser.parse(BilibiliLink("live", "456", "")))
    assert (video.kind, video.event_id, video.author_name) == ("video", "BV1xx411c7mD", "UP")
    assert video.cover_urls == ["https://i0.hdslb.com/video-cover.jpg"]
    assert (live.kind, live.event_id) == ("live_start", "456:live")
