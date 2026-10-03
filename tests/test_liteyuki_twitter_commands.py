from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from test_liteyuki_twitter_state import state


class Finished(Exception): pass


class Matcher:
    def __init__(self): self.sent = []
    async def finish(self, message=""): raise Finished(message)
    async def send(self, message): self.sent.append(message)


def setup_service(tmp_path, monkeypatch):
    Config, Post, store, _ = state(tmp_path)
    from src.nonebot_plugins import liteyuki_twitter
    from src.nonebot_plugins.liteyuki_twitter import commands, group_settings, runtime
    config = Config(twitter_enabled=True, twitter_group_ids=[101, 202], twitter_follows=["example"])
    service = runtime.TwitterService(config, store)
    monkeypatch.setattr(liteyuki_twitter, "config", config)
    monkeypatch.setattr(commands, "get_service", lambda: service)
    groups = {}
    class DB:
        def save(self, group): groups[group.group_id] = group
    def model(group):
        return DB(), groups.get(str(group), SimpleNamespace(group_id=str(group), config={}))
    monkeypatch.setattr(group_settings, "group_model", model)
    async def core(*args, **kwargs): return True
    monkeypatch.setattr(group_settings, "core_allowed", core)
    async def superuser(bot, event): return event.user_id == "99"
    monkeypatch.setattr(commands, "is_superuser", superuser)
    async def message(bot, post): return post.text
    monkeypatch.setattr(service, "message", message)
    event = SimpleNamespace(group_id=101, user_id="2", get_user_id=lambda: "2", get_plaintext=lambda: "https://x.com/example/status/100")
    return commands, group_settings, runtime, service, Post, event


def invoke(handler, args, event, matcher=None):
    return asyncio.run(handler(SimpleNamespace(main_args={"raw": args}), event, None, matcher or Matcher()))


def test_manage_and_follow_other_group_superuser_boundary(tmp_path, monkeypatch):
    commands, groups, _, service, _, event = setup_service(tmp_path, monkeypatch)
    with pytest.raises(Finished, match="SUPERUSER"):
        invoke(commands.handle_follow, ["other", "--群", "202"], event)
    event.user_id = "99"
    with pytest.raises(Finished, match="已关注"):
        invoke(commands.handle_follow, ["@Other", "--仅媒体", "--回复", "--群", "202"], event)
    assert service.store.follows(service.config, "202")["other"][0].replies
    assert "other" not in service.store.follows(service.config, "101")
    with pytest.raises(Finished, match="允许名单"):
        invoke(commands.handle_follow, ["other", "--群", "303"], event)
    with pytest.raises(Finished, match="已更新"):
        invoke(commands.handle_manage, ["命令", "关"], event)
    assert not groups.locally_allowed(service.config, "101", "commands")
    assert groups.locally_allowed(service.config, "101", "push")
    # Management remains usable after the manual query switch is off.
    with pytest.raises(Finished, match="已更新"):
        invoke(commands.handle_manage, ["命令", "开"], event)
    assert groups.locally_allowed(service.config, "101", "commands")
    with pytest.raises(Finished, match="已取关"):
        invoke(commands.handle_unfollow, ["example"], event)
    assert "example" not in service.store.follows(service.config, "101")
    with pytest.raises(Finished, match="恢复配置"):
        invoke(commands.handle_manage, ["订阅重置"], event)
    assert "example" in service.store.follows(service.config, "101")


def test_manual_query_and_link_dedup_do_not_advance_baselines(tmp_path, monkeypatch):
    commands, groups, _, service, Post, event = setup_service(tmp_path, monkeypatch)
    calls = []
    async def status(*args): calls.append(args); return Post("100", "example", text="original")
    monkeypatch.setattr(service, "status_post", status)
    matcher = Matcher()
    invoke(commands.handle_parse, [event.get_plaintext()], event, matcher)
    assert matcher.sent == ["original"]
    link_matcher = Matcher()
    asyncio.run(commands.handle_link(event, None, link_matcher))
    asyncio.run(commands.handle_link(event, None, link_matcher))
    assert link_matcher.sent == ["original"] and len(calls) == 2
    invoke(commands.handle_parse, [event.get_plaintext()], event, matcher)
    assert matcher.sent == ["original", "original"]
    groups.update(service.config, "101", links=False)
    asyncio.run(commands.handle_link(event, None, link_matcher))
    assert len(calls) == 3
    with service.store.connect() as db:
        assert db.execute("SELECT count(*) FROM baselines").fetchone()[0] == 0


def test_private_query_translation_cooldown_and_failure_notes(tmp_path, monkeypatch):
    commands, _, _, service, Post, event = setup_service(tmp_path, monkeypatch)
    event.group_id = None
    async def status(*args): return Post("100", "example", text="original")
    monkeypatch.setattr(service, "status_post", status)
    translated = []
    async def message(bot, post): translated.append(post); return post.text + post.translation_note
    monkeypatch.setattr(service, "message", message)
    matcher = Matcher()
    invoke(commands.handle_translate, [event.get_plaintext()], event, matcher)
    assert translated[0].text == "original" and "尚未配置" in translated[0].translation_note
    with pytest.raises(Finished, match="频繁"):
        invoke(commands.handle_translate, [event.get_plaintext()], event, matcher)


def test_sending_rechecks_disabled_group(tmp_path, monkeypatch):
    commands, groups, _, service, Post, event = setup_service(tmp_path, monkeypatch)
    async def message(bot, post):
        groups.update(service.config, "101", commands=False)
        return "card"
    monkeypatch.setattr(service, "message", message)
    async def status(*args): return Post("100", "example", text="original")
    monkeypatch.setattr(service, "status_post", status)
    matcher = Matcher()
    invoke(commands.handle_parse, [event.get_plaintext()], event, matcher)
    assert matcher.sent == []


@pytest.mark.parametrize("v11", [True, False])
def test_delivery_adapters_and_multi_bot_selection(tmp_path, monkeypatch, v11):
    _, _, runtime, service, Post, _ = setup_service(tmp_path, monkeypatch)
    sent = []
    class V11:
        async def send_group_msg(self, **kwargs): sent.append(kwargs)
    class V12:
        async def call_api(self, api, **kwargs): sent.append((api, kwargs))
    bot = V11() if v11 else V12()
    monkeypatch.setattr(runtime.nonebot, "get_bots", lambda: {"1": bot})
    assert asyncio.run(service.deliver("101", Post("100", "example", text="original")))
    if v11:
        assert sent == [{"group_id": 101, "message": "original"}]
    else:
        assert sent == [("send_message", {"detail_type": "group", "group_id": "101", "message": "original"})]
    monkeypatch.setattr(runtime.nonebot, "get_bots", lambda: {"1": bot, "2": bot})
    assert runtime.choose_bot(service.config) is None
    service.config.twitter_push_bot_id = "2"
    assert runtime.choose_bot(service.config) is bot


def test_core_disable_and_access_checks(monkeypatch):
    from test_liteyuki_twitter_parser import modules
    modules()
    import nonebot
    nonebot.require("src.nonebot_plugins.liteyuki_pacman")
    nonebot.require("src.nonebot_plugins.liteyuki_access_control")
    from src.nonebot_plugins.liteyuki_twitter import group_settings
    from src.nonebot_plugins.liteyuki_pacman import common
    from src.nonebot_plugins.liteyuki_access_control import api
    switches = {"global": True, "group": True, "session": True, "access": True}
    monkeypatch.setattr(common, "get_plugin_global_enable", lambda _: switches["global"])
    monkeypatch.setattr(common, "get_group_enable", lambda _: switches["group"])
    monkeypatch.setattr(common, "get_plugin_session_enable", lambda *_: switches["session"])
    async def access(*args, **kwargs): return switches["access"]
    monkeypatch.setattr(api, "is_allowed", access)
    assert asyncio.run(group_settings.core_allowed("101"))
    for key in switches:
        switches[key] = False
        assert not asyncio.run(group_settings.core_allowed("101"))
        switches[key] = True


@pytest.mark.parametrize("change", ["unfollow", "disable"])
def test_delivery_rechecks_subscription_after_render(tmp_path, monkeypatch, change):
    _, groups, runtime, service, Post, _ = setup_service(tmp_path, monkeypatch)
    sent = []
    class Bot:
        async def send_group_msg(self, **kwargs): sent.append(kwargs)
    monkeypatch.setattr(runtime.nonebot, "get_bots", lambda: {"1": Bot()})
    async def message(bot, post):
        if change == "unfollow":
            service.store.unfollow("101", "example")
        else:
            groups.update(service.config, "101", push=False)
        return "card"
    monkeypatch.setattr(service, "message", message)
    assert not asyncio.run(service.deliver("101", Post("100", "example", text="original")))
    assert sent == []
