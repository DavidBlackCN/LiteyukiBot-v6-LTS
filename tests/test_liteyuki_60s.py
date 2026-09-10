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


def test_group_mode_scopes_commands_and_pushes(monkeypatch) -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_60s.config import SixtyApiConfig
    from src.nonebot_plugins.liteyuki_60s.scheduler import push_content
    from src.nonebot_plugins.liteyuki_60s.service import Content, group_allowed

    whitelist = SixtyApiConfig(sixty_api_group_ids=[10001])
    assert group_allowed(whitelist, 10001)
    assert not group_allowed(whitelist, 10002)
    assert group_allowed(whitelist, None)
    blacklist = SixtyApiConfig(sixty_api_group_mode="blacklist", sixty_api_group_ids=[10001])
    assert not group_allowed(blacklist, 10001)
    assert group_allowed(blacklist, 10002)

    class Bot:
        def __init__(self):
            self.sent = []
            self.messages = []

        async def get_group_list(self):
            return [{"group_id": 10001}, {"group_id": 10002}]

        async def send_group_msg(self, *, group_id, message):
            self.sent.append(group_id)
            self.messages.append(message)

    bot = Bot()

    async def content(*_args):
        return Content("text", "test")

    monkeypatch.setattr("src.nonebot_plugins.liteyuki_60s.scheduler.choose_push_bot", lambda _config: bot)
    monkeypatch.setattr("src.nonebot_plugins.liteyuki_60s.scheduler.fetch_content", content)
    assert asyncio.run(push_content(whitelist, "world"))
    assert bot.sent == [10001]
    bot.sent.clear()
    assert asyncio.run(push_content(blacklist, "world"))
    assert bot.sent == [10002]

    calls = []

    async def random_content(_config, feature, *, name=None):
        calls.append((feature, name))
        return Content("text", f"{feature}-{len(calls)}")

    monkeypatch.setattr("src.nonebot_plugins.liteyuki_60s.scheduler.fetch_content", random_content)
    random_groups = SixtyApiConfig(sixty_api_group_ids=[10001, 10002], sixty_api_fabing_default_name="小明")
    bot.sent.clear()
    bot.messages.clear()
    assert asyncio.run(push_content(random_groups, "fabing", per_group_random=True))
    assert bot.sent == [10001, 10002]
    assert bot.messages == ["fabing-1", "fabing-2"]
    assert calls == [("fabing", "小明"), ("fabing", "小明")]

    calls.clear()
    bot.sent.clear()
    bot.messages.clear()
    assert asyncio.run(push_content(random_groups, "dad_joke", per_group_random=True))
    assert bot.sent == [10001, 10002]
    assert bot.messages == ["dad_joke-1", "dad_joke-2"]
    assert calls == [("dad_joke", None), ("dad_joke", None)]




def test_random_group_pushes_have_independent_schedules(monkeypatch) -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_60s import scheduler as scheduler_module
    from src.nonebot_plugins.liteyuki_60s.config import SixtyApiConfig

    class Job:
        def __init__(self, job_id, func, kwargs):
            self.id = job_id
            self.func = func
            self.kwargs = kwargs

    class FakeScheduler:
        def __init__(self):
            self.jobs = {}

        def get_job(self, job_id):
            return self.jobs.get(job_id)

        def get_jobs(self):
            return list(self.jobs.values())

        def remove_job(self, job_id):
            self.jobs.pop(job_id, None)

        def add_job(self, func, _trigger, *, id, **kwargs):
            self.jobs[id] = Job(id, func, kwargs)

    fake_scheduler = FakeScheduler()
    run_times = iter((
        datetime(2026, 1, 1, 10, 5, tzinfo=ZoneInfo("Asia/Shanghai")),
        datetime(2026, 1, 1, 10, 35, tzinfo=ZoneInfo("Asia/Shanghai")),
    ))
    config = SixtyApiConfig(
        sixty_api_group_mode="blacklist",
        sixty_api_fabing_random_push_enabled=True,
    )

    monkeypatch.setattr(scheduler_module, "scheduler", fake_scheduler)
    class Bot:
        async def get_group_list(self):
            return [{"group_id": 10001}, {"group_id": 10002}]

    monkeypatch.setattr(scheduler_module, "choose_push_bot", lambda _config: Bot())
    monkeypatch.setattr(scheduler_module, "next_random_time", lambda *_args: next(run_times))
    monkeypatch.setattr(scheduler_module.random, "randint", lambda *_args: 10)
    scheduler_module._schedule_random(config, "fabing")

    bootstrap = fake_scheduler.jobs["liteyuki_60s.fabing_random"]
    asyncio.run(bootstrap.func())

    first = fake_scheduler.jobs["liteyuki_60s.fabing_random.10001"]
    second = fake_scheduler.jobs["liteyuki_60s.fabing_random.10002"]
    assert first.kwargs["run_date"] != second.kwargs["run_date"]


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
