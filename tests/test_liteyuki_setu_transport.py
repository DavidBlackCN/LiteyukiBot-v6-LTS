from __future__ import annotations

import asyncio
import base64
from unittest.mock import patch

import aiohttp

import nonebot
import pytest


def _init() -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()


class _Response:
    status = 200
    headers = {"Content-Type": "image/png"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def json(self, **_kwargs):
        return {"ok": True}

    async def read(self):
        return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC")


class _Session:
    def __init__(self) -> None:
        self.request_calls = []
        self.get_calls = []

    def request(self, *args, **kwargs):
        self.request_calls.append((args, kwargs))
        return _Response()

    def get(self, *args, **kwargs):
        self.get_calls.append((args, kwargs))
        return _Response()


def test_http_client_passes_proxy_and_image_headers_per_request() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.network import HttpClient

    session = _Session()
    client = HttpClient(10, session=session)
    assert asyncio.run(client.request_json("GET", "https://api.example/data", proxy=None)) == {"ok": True}
    image = asyncio.run(client.download_image(
        "https://i.pximg.net/img.jpg", max_bytes=1024,
        headers={"Referer": "https://www.pixiv.net/"}, proxy="http://127.0.0.1:7890",
    ))
    assert image
    assert session.request_calls[0][1]["proxy"] is None
    assert session.get_calls[0][1]["proxy"] == "http://127.0.0.1:7890"
    assert session.get_calls[0][1]["headers"] == {"Referer": "https://www.pixiv.net/"}


class _LoliconClient:
    def __init__(self) -> None:
        self.calls = []

    async def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return {"data": [{"pid": 1, "r18": False, "urls": {"regular": "https://i.pximg.net/a.jpg"}}]}


def test_lolicon_api_is_direct_by_default_and_keeps_pixiv_host_payload() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.lolicon import LoliconProvider

    client = _LoliconClient()
    asyncio.run(LoliconProvider(client, "https://api.lolicon.app/setu/v2", "i.pximg.net").fetch(ImageQuery()))
    request = client.calls[0][2]
    assert request["proxy"] is None
    assert request["json"]["proxy"] == "i.pximg.net"


class _DownloadClient:
    def __init__(self) -> None:
        self.calls = []

    async def download_image(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return b"image"


def test_only_lolicon_pximg_download_uses_proxy_and_pixiv_headers() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.models import ImageResult
    from src.nonebot_plugins.liteyuki_setu.service import download_results

    client = _DownloadClient()
    config = SetuConfig(setu_lolicon_image_http_proxy="http://127.0.0.1:7890")
    results = asyncio.run(download_results([
        ImageResult(provider="lolicon", image_url="https://i.pximg.net/a.jpg"),
        ImageResult(provider="mirlkoi", image_url="https://setu.iw233.top/a.jpg"),
    ], config, client=client))
    assert len(results) == 2
    calls = {url: options for url, options in client.calls}
    assert calls["https://i.pximg.net/a.jpg"]["proxy"] == "http://127.0.0.1:7890"
    assert calls["https://i.pximg.net/a.jpg"]["headers"] == {
        "Referer": "https://www.pixiv.net/", "User-Agent": "Mozilla/5.0",
    }
    assert calls["https://setu.iw233.top/a.jpg"]["proxy"] is None
    assert calls["https://setu.iw233.top/a.jpg"]["headers"] is None


def test_api_and_image_timeouts_are_independent_with_legacy_fallback() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.service import _api_timeout, _image_timeout

    assert _api_timeout(SetuConfig(setu_api_timeout=10, setu_image_timeout=30)) == 10
    assert _image_timeout(SetuConfig(setu_api_timeout=10, setu_image_timeout=30)) == 30
    legacy = SetuConfig(setu_request_timeout=15)
    assert _api_timeout(legacy) == 15
    assert _image_timeout(legacy) == 15


class _FallbackClient:
    async def request_json(self, _method, url, **_kwargs):
        if "lolicon" in url:
            from src.nonebot_plugins.liteyuki_setu.models import ProviderError
            raise ProviderError("图片源请求失败: ClientConnectionError: proxy connection refused")
        return {"pic": ["https://setu.iw233.top/large/example.jpg"]}


def test_proxy_failure_logs_provider_reason_and_preserves_auto_fallback(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu import service
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery

    monkeypatch.setattr(service, "health", service.ProviderHealth())
    config = SetuConfig(setu_exclude_ai=False, setu_request_retries=0)
    with patch.object(service.logger, "warning") as warning:
        result = asyncio.run(service.fetch_images(ImageQuery(exclude_ai=False), config, client=_FallbackClient()))
    assert result[0].provider == "mirlkoi"
    assert any("Lolicon API 请求失败" in str(call.args[0]) and "proxy connection refused" in str(call.args[0])
               for call in warning.call_args_list)

class _ProxyFailureSession:
    def request(self, *_args, **_kwargs):
        raise aiohttp.ClientConnectionError("proxy connection refused")


def test_proxy_connection_failure_is_logged_and_wrapped_as_provider_error() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ProviderError
    from src.nonebot_plugins.liteyuki_setu.network import HttpClient, logger

    with patch.object(logger, "warning") as warning:
        with pytest.raises(ProviderError, match="ClientConnectionError: proxy connection refused"):
            asyncio.run(HttpClient(10, retries=0, session=_ProxyFailureSession()).request_json(
                "GET", "https://api.lolicon.app/setu/v2", proxy="http://127.0.0.1:7890",
            ))
    assert "host=api.lolicon.app" in str(warning.call_args.args[0])

class _ImageFailureClient:
    async def download_image(self, _url, **_kwargs):
        from src.nonebot_plugins.liteyuki_setu.models import ProviderError
        raise ProviderError("图片下载失败: ClientProxyConnectionError: proxy connection refused")


def test_lolicon_image_proxy_failure_logs_provider_host_and_reason() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu import service
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.models import ImageResult

    result = ImageResult(provider="lolicon", image_url="https://i.pximg.net/a.jpg")
    with patch.object(service.logger, "warning") as warning:
        assert asyncio.run(service.download_results([result], SetuConfig(), client=_ImageFailureClient())) == []
    message = str(warning.call_args.args[0])
    assert "Lolicon 图片下载失败" in message
    assert "host=i.pximg.net" in message
    assert "proxy connection refused" in message