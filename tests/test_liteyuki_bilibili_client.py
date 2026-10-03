import asyncio

import httpx
import pytest

from src.nonebot_plugins.liteyuki_bilibili.client import BilibiliClient, _sign_wbi_params
from src.nonebot_plugins.liteyuki_bilibili.config import BilibiliConfig
from src.nonebot_plugins.liteyuki_bilibili.credential import CredentialManager
from src.nonebot_plugins.liteyuki_bilibili.errors import (
    BilibiliAPIError,
    BilibiliCredentialError,
    BilibiliRateLimitError,
)


def run(coroutine):
    return asyncio.run(coroutine)


def test_nav_uses_shared_cookie_and_normalizes_response() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Cookie"] == "SESSDATA=test"
            return httpx.Response(200, json={"code": 0, "data": {"isLogin": True, "mid": 7, "uname": "UP"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager("SESSDATA=test", MemoryStore()), http_client)
            nav = await client.get_nav()
        assert nav.is_login is True
        assert nav.mid == "7"
        assert nav.username == "UP"

    run(scenario())


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(200, text="not json"), BilibiliAPIError),
        (httpx.Response(200, json={"code": -101, "data": {}}), BilibiliCredentialError),
        (httpx.Response(412), BilibiliRateLimitError),
    ],
)
def test_api_failures_are_mapped_to_expected_errors(response: httpx.Response, error: type[Exception]) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            with pytest.raises(error):
                await client.get_nav()

    run(scenario())


def test_short_link_rejects_untrusted_redirect() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(302, headers={"location": "https://example.invalid/"})
            )
        ) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            with pytest.raises(BilibiliAPIError):
                await client.resolve_short_url("https://b23.tv/test")

    run(scenario())


def test_dynamic_list_is_normalized_without_exposing_api_json() -> None:
    async def scenario() -> None:
        payload = {
            "code": 0,
            "data": {
                "items": [
                    {
                        "id_str": "9988",
                        "modules": {
                            "module_author": {"mid": 7, "name": "UP", "face": "avatar"},
                            "module_dynamic": {
                                "desc": {"text": "测试动态"},
                                "major": {"draw": {"items": [{"src": "image"}]}},
                            },
                        },
                    }
                ]
            },
        }
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            events = await client.get_latest_dynamics("7")
        assert events[0].event_id == "9988"
        assert events[0].author_name == "UP"
        assert events[0].cover_urls == ["image"]

    run(scenario())


def test_video_info_maps_bilibili_pic_to_cover_url() -> None:
    async def scenario() -> None:
        payload = {
            "code": 0,
            "data": {
                "bvid": "BV1xx411c7mD",
                "title": "测试视频",
                "pic": "//i0.hdslb.com/video-cover.jpg",
                "owner": {"mid": 42, "name": "UP", "face": "http://i1.hdslb.com/avatar.jpg"},
            },
        }
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            video = await client.get_video_info(bvid="BV1xx411c7mD")
        assert video.cover_url == "//i0.hdslb.com/video-cover.jpg"
        assert video.avatar_url == "http://i1.hdslb.com/avatar.jpg"

    run(scenario())


def test_live_status_keeps_room_id_when_old_endpoint_has_no_cover() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/room/v1/Room/getRoomInfoOld"
            return httpx.Response(
                200,
                json={"code": 0, "data": {"room_id": 100, "live_status": 1, "title": "基础直播"}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            status = await client.get_live_status("42")
        assert status.room_id == "100" and status.live and status.cover_url == ""

    run(scenario())


@pytest.mark.parametrize(
    ("detail", "expected_cover"),
    [
        ({"user_cover": "//i0.hdslb.com/live-cover.jpg", "keyframe": "//i0.hdslb.com/keyframe.jpg"}, "//i0.hdslb.com/live-cover.jpg"),
        ({"user_cover": "", "keyframe": "//i0.hdslb.com/keyframe.jpg"}, "//i0.hdslb.com/keyframe.jpg"),
    ],
)
def test_live_room_status_prefers_user_cover_then_keyframe(detail, expected_cover: str) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/room/v1/Room/get_info"
            assert request.url.params["room_id"] == "100"
            return httpx.Response(
                200,
                json={"code": 0, "data": {"uid": 42, "room_id": 100, "live_status": 1, **detail}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            status = await client.get_live_room_status("100")
        assert status.cover_url == expected_cover
        assert status.url == "https://live.bilibili.com/100"

    run(scenario())


def test_dynamic_normalizes_opus_pictures() -> None:
    event = BilibiliClient._dynamic_from_api(
        {
            "id_str": "1",
            "modules": {
                "module_author": {"mid": 7},
                "module_dynamic": {"major": {"opus": {"pics": [{"url": "opus-image"}]}}},
            },
        }
    )
    assert event.cover_urls == ["opus-image"]


def test_latest_videos_uses_wbi_signature_and_refreshes_after_403(monkeypatch) -> None:
    async def scenario() -> None:
        calls = {"nav": 0, "videos": 0}
        key_material = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/x/web-interface/nav":
                calls["nav"] += 1
                return httpx.Response(
                    200,
                    json={
                        "code": 0,
                        "data": {
                            "wbi_img": {
                                "img_url": f"https://i0.hdslb.com/{key_material[:32]}.png",
                                "sub_url": f"https://i0.hdslb.com/{key_material[32:]}.png",
                            }
                        },
                    },
                )
            assert request.url.host == "api.bilibili.com"
            assert request.url.path == "/x/space/wbi/arc/search"
            assert request.url.params["wts"] == "1700000000"
            assert request.url.params["w_rid"]
            calls["videos"] += 1
            if calls["videos"] == 1:
                return httpx.Response(200, json={"code": -403, "data": {}})
            return httpx.Response(
                200,
                json={"code": 0, "data": {"list": {"vlist": [{"bvid": "BV1test"}]}}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            videos = await client.get_latest_videos("453841968")
        assert [video.bvid for video in videos] == ["BV1test"]
        assert calls == {"nav": 2, "videos": 2}

    monkeypatch.setattr("src.nonebot_plugins.liteyuki_bilibili.client.time.time", lambda: 1700000000)
    run(scenario())


def test_wbi_signature_removes_reserved_characters() -> None:
    signed = _sign_wbi_params(
        {
            "mid": "453841968",
            "pn": 1,
            "ps": 3,
            "order": "pubdate",
            "keyword": "a!'()*b",
        },
        "0123456789abcdefghijklmnopqrstuv",
        timestamp=1700000000,
    )
    assert signed["w_rid"] == "eb815be96bae17ddeba3818c301daf4d"


def test_dynamic_share_video_covers_are_normalized() -> None:
    async def scenario() -> None:
        payload = {
            "code": 0,
            "data": {
                "items": [
                    {
                        "id_str": "additional-share",
                        "modules": {
                            "module_author": {"mid": 7, "name": "UP"},
                            "module_dynamic": {
                                "additional": {
                                    "type": "ADDITIONAL_TYPE_UGC",
                                    "ugc": {"title": "分享视频", "cover": "//i0.hdslb.com/share.jpg"},
                                }
                            },
                        },
                    },
                    {
                        "id_str": "forward-share",
                        "modules": {
                            "module_author": {"mid": 7, "name": "UP"},
                            "module_dynamic": {"desc": {"text": "转发视频"}},
                        },
                        "orig": {
                            "modules": {
                                "module_dynamic": {
                                    "major": {
                                        "archive": {
                                            "title": "原视频",
                                            "cover": "//i1.hdslb.com/original.jpg",
                                        }
                                    }
                                }
                            }
                        },
                    },
                ]
            },
        }
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            events = await client.get_latest_dynamics("7")
        assert events[0].title == "分享视频"
        assert events[0].cover_urls == ["//i0.hdslb.com/share.jpg"]
        assert events[1].title == "原视频"
        assert events[1].cover_urls == ["//i1.hdslb.com/original.jpg"]

    run(scenario())


def test_image_download_is_limited_to_bilibili_cdn_and_image_content() -> None:
    async def scenario() -> None:
        requested_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            return httpx.Response(200, headers={"content-type": "image/png"}, content=b"png")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            image = await client.download_image("https://i0.hdslb.com/cover.png")
            assert image.data == b"png" and image.content_type == "image/png"
            await client.download_image("//i1.hdslb.com/cover.png")
            await client.download_image("http://i2.hdslb.com/cover.png")
            with pytest.raises(BilibiliAPIError):
                await client.download_image("https://example.invalid/image.png")
        assert requested_urls == [
            "https://i0.hdslb.com/cover.png",
            "https://i1.hdslb.com/cover.png",
            "https://i2.hdslb.com/cover.png",
        ]

    run(scenario())


def test_qr_generate_uses_passport_host() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "passport.bilibili.com"
            assert request.url.path == "/x/passport-login/web/qrcode/generate"
            return httpx.Response(
                200,
                json={"code": 0, "data": {"url": "https://login.example/qr", "qrcode_key": "key"}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            session = await client.create_qr_login()
        assert session.url == "https://login.example/qr"
        assert session.key == "key"

    run(scenario())


@pytest.mark.parametrize(
    ("qr_code", "status"),
    [(86101, "waiting"), (86090, "scanned"), (86038, "expired"), (0, "confirmed")],
)
def test_qr_poll_reads_status_from_data_code(qr_code: int, status: str) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "passport.bilibili.com"
            assert request.url.path == "/x/passport-login/web/qrcode/poll"
            assert request.url.params["qrcode_key"] == "one-time-key"
            return httpx.Response(
                200,
                headers=[
                    ("set-cookie", "SESSDATA=session; Path=/; HttpOnly"),
                    ("set-cookie", "bili_jct=csrf; Path=/"),
                ],
                json={"code": 0, "data": {"code": qr_code, "refresh_token": "refresh"}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            result = await client.poll_qr_login("one-time-key")
        assert result.status == status
        if status == "confirmed":
            assert result.cookie == "SESSDATA=session; bili_jct=csrf"
            assert result.refresh_token == "refresh"
        else:
            assert result.cookie == ""

    run(scenario())


def test_qr_poll_checks_outer_api_code_before_qr_status() -> None:
    async def scenario() -> None:
        response = httpx.Response(200, json={"code": -101, "data": {"code": 0}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            with pytest.raises(BilibiliCredentialError):
                await client.poll_qr_login("one-time-key")

    run(scenario())


class MemoryStore:
    def load(self) -> str:
        return ""

    def save(self, cookie: str) -> None:
        pass

    def clear(self) -> None:
        pass


def _dynamic_fixture(major=None, desc=None, **extra):
    return {"id_str": "123", "modules": {
        "module_author": {"mid": 7, "name": "作者"},
        "module_dynamic": {"major": major or {}, "desc": desc}}, **extra}


def test_opus_title_summary_and_complete_pictures():
    event = BilibiliClient._dynamic_from_api(_dynamic_fixture({"opus": {
        "title": "图文标题", "summary": {"text": "第一行\n第二行"},
        "pics": [{"url": f"image-{i}"} for i in range(9)]}}))
    assert event.title == "图文标题"
    assert event.body == "第一行\n第二行"
    assert len(event.cover_urls) == 9


def test_rich_text_fallback_and_desc_precedence():
    major = {"opus": {"summary": {"rich_text_nodes": [
        {"text": "正文\n"}, {"orig_text": "[表情]"}, {"text": "话题"}]}}}
    event = BilibiliClient._dynamic_from_api(_dynamic_fixture(major))
    assert event.body == "正文\n[表情]话题"
    event = BilibiliClient._dynamic_from_api(_dynamic_fixture(major, {"text": "优先正文"}))
    assert event.body == "优先正文"


def test_forward_keeps_comment_and_original_text_separate():
    original = _dynamic_fixture({"opus": {"title": "原标题", "summary": {"text": "原正文"},
                                                "pics": [{"url": "原图"}]}})
    event = BilibiliClient._dynamic_from_api(_dynamic_fixture(desc={"text": "转发评论"}, orig=original))
    assert event.kind == "dynamic" and event.display_type == "forward"
    assert event.body == "转发评论"
    assert event.original.author_name == "作者"
    assert event.original.body == "原正文" and event.original.title == "原标题"
    assert event.original.cover_urls == ["原图"]


def test_unavailable_original_has_explicit_state():
    event = BilibiliClient._dynamic_from_api(_dynamic_fixture(orig={"type": "DYNAMIC_TYPE_NONE"}))
    assert event.original.unavailable


@pytest.mark.parametrize("as_json", [True, False])
def test_live_recommendation_preserves_dynamic_kind(as_json):
    import json
    content = {"live_play_info": {"room_id": 42, "title": "直播标题", "cover": "直播封面",
                                  "area_name": "游戏", "live_status": 1}}
    event = BilibiliClient._dynamic_from_api(_dynamic_fixture({"live_rcmd": {
        "content": json.dumps(content) if as_json else content}}))
    assert event.kind == "dynamic" and event.display_type == "live"
    assert event.title == "直播标题" and event.cover_urls == ["直播封面"]
    assert event.live.url == "https://live.bilibili.com/42"
    assert event.live.area_name == "游戏" and event.live.state == "正在直播"


def test_live_major_and_malformed_recommendation_are_isolated():
    event = BilibiliClient._dynamic_from_api(_dynamic_fixture({
        "live": {"id": 42, "title": "直播", "cover": "封面"},
        "live_rcmd": {"content": "invalid-json"}}, desc={"text": "正文"}))
    assert event.live.url == "https://live.bilibili.com/42" and event.body == "正文"
    event = BilibiliClient._dynamic_from_api(_dynamic_fixture({"live_rcmd": {"content": "[]"}}))
    assert event.live is None and event.kind == "dynamic"


def test_forward_retains_legacy_cover_list_without_losing_own_media():
    original = _dynamic_fixture({"draw": {"items": [{"src": "original-image"}]}})
    event = BilibiliClient._dynamic_from_api(_dynamic_fixture(
        {"draw": {"items": [{"src": "own-image"}]}}, orig=original))
    assert event.cover_urls == ["own-image", "original-image"]
    assert event.original.cover_urls == ["original-image"]
