import asyncio

import httpx
import pytest

from src.nonebot_plugins.liteyuki_bilibili.client import BilibiliClient
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
                "pic": "https://i0.hdslb.com/video-cover.jpg",
                "owner": {"mid": 42, "name": "UP"},
            },
        }
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            video = await client.get_video_info(bvid="BV1xx411c7mD")
        assert video.cover_url == "https://i0.hdslb.com/video-cover.jpg"

    run(scenario())


def test_image_download_is_limited_to_bilibili_cdn_and_image_content() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, headers={"content-type": "image/png"}, content=b"png")
            )
        ) as http_client:
            client = BilibiliClient(BilibiliConfig(), CredentialManager(store=MemoryStore()), http_client)
            image = await client.download_image("https://i0.hdslb.com/cover.png")
            assert image.data == b"png" and image.content_type == "image/png"
            with pytest.raises(BilibiliAPIError):
                await client.download_image("https://example.invalid/image.png")

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
