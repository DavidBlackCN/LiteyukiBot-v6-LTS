from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import aiohttp
import nonebot
import pytest


class FakeResponse:
    def __init__(self, status=200, payload=None, body=b"image", json_error=False):
        self.status = status
        self.payload = payload
        self.body = body
        self.json_error = json_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self, **kwargs):
        if self.json_error:
            raise ValueError("bad json")
        return self.payload

    async def read(self):
        return self.body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.response


def test_client_url_and_errors():
    from src.nonebot_plugins.liteyuki_60s.client import SixtyApiClient, SixtyApiError

    async def main():
        session = FakeSession(FakeResponse(payload={"code": 200, "data": {"ok": 1}}))
        client = SixtyApiClient("https://example.test/prefix/", session=session)
        assert client.endpoint("/v2/60s") == "https://example.test/prefix/v2/60s"
        assert await client.get_data("/v2/60s") == {"ok": 1}
        assert session.requests[0][0].endswith("/prefix/v2/60s")
        for response in (FakeResponse(status=500), FakeResponse(payload={"code": 500, "message": "no"}), FakeResponse(json_error=True), FakeResponse(payload={"code": 200, "data": None})):
            try:
                await SixtyApiClient("https://example.test", session=FakeSession(response)).get_data("v2/test")
            except SixtyApiError:
                pass
            else:
                raise AssertionError("invalid response was accepted")
        assert await SixtyApiClient("https://example.test", session=FakeSession(FakeResponse())).download_image("https://image.test/a.png") == b"image"
        try:
            await SixtyApiClient("https://example.test", session=FakeSession(FakeResponse(status=404))).download_image("https://image.test/a.png")
        except SixtyApiError:
            pass
        else:
            raise AssertionError("failed image was accepted")
    asyncio.run(main())


def test_service_content_choices(monkeypatch):
    from src.nonebot_plugins.liteyuki_60s import service
    from src.nonebot_plugins.liteyuki_60s.config import SixtyApiConfig
    from src.nonebot_plugins.liteyuki_60s.client import SixtyApiError

    class Client:
        image_fails = False
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get_data(self, path, params=None):
            if path.endswith("60s"): return {"image": "https://image.test/world.png", "news": [{"title": "news"}]}
            if path.endswith("ai-news"): return {"news": []}
            if path.endswith("fabing"): return {"saying": "发病文字"}
            if path.endswith("kfc"): return {"kfc": "KFC 文字"}
            if path.endswith("dad-joke"): return {"content": "笑话文字"}
            return {"news": [{"title": "news"}]}
        async def download_image(self, url):
            if self.image_fails: raise SixtyApiError("offline")
            return b"remote-image"

    async def main():
        monkeypatch.setattr(service, "SixtyApiClient", Client)
        from src.nonebot_plugins.liteyuki_60s import cards
        monkeypatch.setattr(cards, "render_card", lambda *args, **kwargs: asyncio.sleep(0, result=b"rendered"))
        config = SixtyApiConfig()
        assert (await service.fetch_content(config, "world")).value == b"remote-image"
        Client.image_fails = True
        assert (await service.fetch_content(config, "world")).value == b"rendered"
        assert (await service.fetch_content(config, "ai")).empty is True
        for feature, expected in (("fabing", "发病文字"), ("kfc", "KFC 文字"), ("dad_joke", "笑话文字")):
            result = await service.fetch_content(config, feature)
            assert result.kind == "text" and result.value == expected
    asyncio.run(main())


def test_luck_state_persists_across_queries():
    from src.nonebot_plugins.liteyuki_60s.state import LuckUsage, can_use_luck, luck_db, record_luck_success

    user_id, day = "pytest-60s-user", "2099-01-01"
    luck_db.delete(LuckUsage(), "user_id = ?", user_id)
    assert can_use_luck(user_id, day, 1)
    record_luck_success(user_id, day)
    assert not can_use_luck(user_id, day, 1)
    assert can_use_luck(user_id, "2099-01-02", 1)


def test_scheduler_helpers_and_command_load():
    nonebot.init()
    from nonebot.adapters.onebot.v11 import Adapter
    from src.liteyuki_plugins.liteyukibot_plugin_nonebot import _load_alconna_plugin
    from src.liteyuki_plugins.liteyukibot_plugin_nonebot import _load_htmlrender_plugin
    nonebot.get_driver().register_adapter(Adapter)
    _load_htmlrender_plugin()
    _load_alconna_plugin()
    _load_htmlrender_plugin()
    assert nonebot.load_plugin("src.nonebot_plugins.liteyuki_60s") is not None
    from src.nonebot_plugins.liteyuki_60s import commands
    from src.nonebot_plugins.liteyuki_60s.scheduler import next_random_time, parse_clock

    assert parse_clock("08:30") == (8, 30)
    with pytest.raises(ValueError): parse_clock("25:00")
    now = datetime(2026, 1, 1, 21, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    target = next_random_time(now, "08:00", "22:00", 180, 180)
    assert target.hour == 8 and target.day == 2
    assert commands.world_command.command().parse("60s").matched
    assert commands.ai_command.command().parse("AI资讯").matched
    assert commands.history_command.command().parse("历史今天").matched
    assert commands.it_command.command().parse("实时IT资讯").matched
    assert commands.moyu_command.command().parse("摸鱼").matched
    assert commands.hitokoto_command.command().parse("随机一言").matched
    assert commands.luck_command.command().parse("今日运势").matched
    assert commands.fabing_command.command().parse("发病文学 叶子").matched
    assert commands.kfc_command.command().parse("疯狂星期四").matched
    assert commands.dad_joke_command.command().parse("随机冷笑话").matched
