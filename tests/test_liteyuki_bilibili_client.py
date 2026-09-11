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


class MemoryStore:
    def load(self) -> str:
        return ""

    def save(self, cookie: str) -> None:
        pass

    def clear(self) -> None:
        pass
