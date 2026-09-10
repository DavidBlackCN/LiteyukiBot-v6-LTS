from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import get_type_hints

import nonebot


class _Finished(Exception):
    pass


class _Matcher:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def finish(self, message=None):
        self.messages.append(str(message))
        raise _Finished

    async def send(self, message):
        self.messages.append(str(message))
        return None


def _v11_group_context():
    from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, Message

    try:
        driver = nonebot.get_driver()
    except ValueError:
        nonebot.init()
        driver = nonebot.get_driver()
    if Adapter.get_name() not in driver._adapters:
        driver.register_adapter(Adapter)
    bot = Bot(driver._adapters[Adapter.get_name()], "setu-test-bot")
    event = GroupMessageEvent(
        time=0, self_id=1, post_type="message", sub_type="normal", user_id=2,
        message_type="group", message_id=3, message=Message("测试"),
        original_message=Message("测试"), raw_message="测试", font=0,
        sender={"role": "admin"}, group_id=10001,
    )
    return bot, event


def test_setu_handlers_receive_nonebot_injected_types_and_reach_runtime_layers(monkeypatch) -> None:
    """Keep handler annotations injectable and exercise them with a real V11 Bot."""
    from nonebot.adapters import Bot, Event
    from nonebot.matcher import Matcher
    from src.nonebot_plugins.liteyuki_setu import admin, commands
    from src.nonebot_plugins.liteyuki_setu.service import Cooldown
    from src.nonebot_plugins.liteyuki_setu.storage import GroupSettings

    assert get_type_hints(commands.handle_setu)["bot"] is Bot
    assert get_type_hints(commands.handle_setu)["event"] is Event
    assert get_type_hints(commands.handle_setu)["matcher"] is Matcher
    assert get_type_hints(admin.handle_admin)["bot"] is Bot
    assert get_type_hints(admin.handle_admin)["event"] is Event
    assert get_type_hints(admin.handle_admin)["matcher"] is Matcher

    bot, event = _v11_group_context()
    from nonebot.adapters.onebot.v11 import Bot as V11Bot
    assert isinstance(bot, V11Bot)
    settings = GroupSettings(True, False, 60, 3, "auto", False, 0, 0)

    async def allow_access(*_args, **_kwargs):
        return True

    requested = []

    async def fetch_images(query, _config):
        requested.append(query)
        return []

    monkeypatch.setattr(commands, "_access_allowed", allow_access)
    monkeypatch.setattr(commands, "group_allowed", lambda *_args: True)
    monkeypatch.setattr(commands, "get_group_settings", lambda *_args: settings)
    monkeypatch.setattr(commands, "fetch_and_download", fetch_images)
    monkeypatch.setattr(commands, "cooldown", Cooldown())
    matcher = _Matcher()
    try:
        asyncio.run(commands.handle_setu(SimpleNamespace(main_args={"raw": ["3", "萝莉"]}), event, bot, matcher))
    except _Finished:
        pass
    else:
        raise AssertionError("色图 handler should finish after the mocked API layer")
    assert requested and requested[0].count == 3 and requested[0].keyword == "萝莉"
    assert matcher.messages[-1] == "图片下载失败，请稍后再试。"

    updates = []
    monkeypatch.setattr(admin, "get_group_settings", lambda *_args: settings)
    monkeypatch.setattr(admin, "update_group_settings", lambda *args, **kwargs: updates.append((args, kwargs)))
    status_matcher = _Matcher()
    try:
        asyncio.run(admin.handle_admin(SimpleNamespace(main_args={"raw": ["状态"]}), event, bot, status_matcher))
    except _Finished:
        pass
    assert "状态：开启" in status_matcher.messages[-1]

    enable_matcher = _Matcher()
    try:
        asyncio.run(admin.handle_admin(SimpleNamespace(main_args={"raw": ["开启"]}), event, bot, enable_matcher))
    except _Finished:
        pass
    assert len(updates) == 1
    assert updates[0][0][0] == "10001"
    assert updates[0][1] == {"enabled": True}
    assert enable_matcher.messages[-1] == "已开启本群全年龄图片功能。"
