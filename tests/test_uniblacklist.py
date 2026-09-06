from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import nonebot
import pytest


nonebot.init()
nonebot.load_plugin("nonebot_plugin_apscheduler")
plugin = nonebot.load_plugin("src.nonebot_plugins.liteyuki_uniblacklist")
assert plugin is not None

from src.nonebot_plugins.liteyuki_uniblacklist import api


class FakeResponse:
    def __init__(self, content: str, status_error: Exception | None = None):
        self.content = content
        self.status_error = status_error
        self.status_checked = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self) -> None:
        self.status_checked = True
        if self.status_error:
            raise self.status_error

    async def text(self) -> str:
        return self.content


class FakeSession:
    response: FakeResponse | None = None
    request_error: Exception | None = None
    received_timeout: aiohttp.ClientTimeout | None = None

    def __init__(self, *, timeout: aiohttp.ClientTimeout):
        type(self).received_timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def get(self, url: str):
        if self.request_error:
            raise self.request_error
        assert url == api.BLACKLIST_URLS["qq"]
        assert self.response is not None
        return self.response


@pytest.fixture(autouse=True)
def isolate_blacklist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(api.aiohttp, "ClientSession", FakeSession)
    api.blacklist_data.clear()
    api._refresh_combined_blacklist()
    FakeSession.response = None
    FakeSession.request_error = None
    FakeSession.received_timeout = None
    yield
    api.blacklist_data.clear()
    api._refresh_combined_blacklist()


def test_successful_update_checks_http_status_and_saves_cache(tmp_path: Path):
    response = FakeResponse("10002\n10001\n")
    FakeSession.response = response

    asyncio.run(api.request_for_blacklist())

    assert response.status_checked
    assert FakeSession.received_timeout is api.HTTP_TIMEOUT
    assert api.blacklist_data["qq"] == {"10001", "10002"}
    assert api.blacklist == {"10001", "10002"}
    assert (tmp_path / "qq.txt").read_text(encoding="utf-8") == (
        "10001\n10002\n"
    )


def test_timeout_keeps_last_in_memory_blacklist():
    api.blacklist_data["qq"] = {"123456"}
    api._refresh_combined_blacklist()
    FakeSession.request_error = asyncio.TimeoutError()

    asyncio.run(api.request_for_blacklist())

    assert api.blacklist_data["qq"] == {"123456"}
    assert api.blacklist == {"123456"}


def test_http_failure_loads_last_valid_disk_cache(tmp_path: Path):
    (tmp_path / "qq.txt").write_text("234567\n345678\n", encoding="utf-8")
    FakeSession.response = FakeResponse(
        "upstream unavailable",
        aiohttp.ClientResponseError(
            request_info=SimpleNamespace(real_url=api.BLACKLIST_URLS["qq"]),
            history=(),
            status=503,
            message="Service Unavailable",
        ),
    )

    asyncio.run(api.request_for_blacklist())

    assert api.blacklist_data["qq"] == {"234567", "345678"}
    assert api.blacklist == {"234567", "345678"}


def test_scheduled_job_does_not_propagate_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fail():
        raise RuntimeError("unexpected")

    monkeypatch.setattr(api, "request_for_blacklist", fail)
    asyncio.run(api.update_blacklist())
