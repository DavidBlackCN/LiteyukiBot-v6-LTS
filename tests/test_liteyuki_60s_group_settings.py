from __future__ import annotations

from types import SimpleNamespace

import asyncio
import nonebot
import pytest


def _modules():
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_60s import group_settings, scheduler
    from src.nonebot_plugins.liteyuki_60s.config import SixtyApiConfig

    return group_settings, scheduler, SixtyApiConfig


def _memory_groups(monkeypatch, group_settings):
    groups = {}

    class Database:
        def save(self, group):
            groups[group.group_id] = group

    def model(group_id):
        return Database(), groups.get(str(group_id), SimpleNamespace(group_id=str(group_id), config={}))

    monkeypatch.setattr(group_settings, "_group_model", model)
    return groups


def test_group_settings_inherit_override_reset_and_boundary(monkeypatch):
    settings, _scheduler, Config = _modules()
    groups = _memory_groups(monkeypatch, settings)
    config = Config(sixty_api_group_ids=[101, 202])

    inherited = settings.get_group_settings(101, config)
    assert inherited["features"]["world"] and inherited["push"]["world"]["time"] == config.sixty_api_world_push_time
    assert inherited["overrides"] == {}

    settings.update_group_settings(101, config, enabled=False)
    assert not settings.feature_allowed(config, 101, "world")
    settings.update_group_settings(101, config, enabled=True, features={"world": {"enabled": False}}, push={"world": {"enabled": True, "time": "08:30"}})
    assert not settings.feature_allowed(config, 101, "world")
    assert settings.resolve_push_settings(config, 101, "world")["time"] == "08:30"
    assert settings.resolve_push_settings(config, 101, "world")["enabled"] is False
    settings.update_group_settings(101, config, features={"world": {"enabled": True}})
    assert settings.resolve_push_settings(config, 101, "world")["enabled"] is True
    settings.reset_group_settings(101, config)
    assert settings.feature_allowed(config, 101, "world")
    assert groups["101"].config.get("liteyuki_60s") is None

    settings.update_group_settings(303, config, enabled=True, features={"world": {"enabled": True}})
    assert not settings.feature_allowed(config, 303, "world")


def test_random_overrides_and_per_group_job_ids(monkeypatch):
    settings, scheduler_module, Config = _modules()
    _memory_groups(monkeypatch, settings)
    config = Config(
        sixty_api_group_ids=[101, 202],
        sixty_api_world_push_enabled=True,
        sixty_api_fabing_random_push_enabled=False,
    )
    settings.update_group_settings(101, config, random_push={"fabing": {
        "enabled": True, "daily_min": 2, "daily_max": 3, "start": "09:00", "end": "21:00",
    }})
    random_values = settings.resolve_random_push_settings(config, 101, "fabing")
    assert (random_values["daily_min"], random_values["daily_max"], random_values["start"]) == (2, 3, "09:00")
    assert settings.resolve_random_push_settings(config, 202, "fabing")["start"] == config.sixty_api_fabing_random_start

    class Job:
        def __init__(self, job_id): self.id = job_id

    class FakeScheduler:
        def __init__(self): self.jobs = {}
        def get_job(self, job_id): return self.jobs.get(job_id)
        def get_jobs(self): return list(self.jobs.values())
        def remove_job(self, job_id): self.jobs.pop(job_id, None)
        def add_job(self, _func, _trigger, *, id, **_kwargs): self.jobs[id] = Job(id)

    fake = FakeScheduler()
    monkeypatch.setattr(scheduler_module, "scheduler", fake)
    monkeypatch.setattr(scheduler_module, "_next_random_run_at", lambda *_args: __import__("datetime").datetime(2099, 1, 1, 10, 0))
    scheduler_module.reschedule_group(config, 101)
    scheduler_module.reschedule_group(config, 202)
    assert "liteyuki_60s.world.101" in fake.jobs
    assert "liteyuki_60s.world.202" in fake.jobs
    scheduler_module.reschedule_group(config, 101)
    assert "liteyuki_60s.world.202" in fake.jobs
    assert all(".101" in job_id or ".202" in job_id for job_id in fake.jobs)


@pytest.mark.parametrize("feature,section,flag", [
    ("world", "push", "sixty_api_world_push_enabled"),
    ("fabing", "random_push", "sixty_api_fabing_random_push_enabled"),
])
def test_command_and_broadcast_switches_are_independent(monkeypatch, feature, section, flag):
    settings, _, Config = _modules()
    groups = _memory_groups(monkeypatch, settings)
    config = Config(sixty_api_group_ids=[101, 202], **{flag: True})
    groups["101"] = SimpleNamespace(group_id="101", config={"unrelated": {"enabled": True}})
    settings.update_group_settings(101, config, commands={feature: {"enabled": False}})
    assert not settings.command_allowed(config, 101, feature)
    assert settings.broadcast_allowed(config, 101, feature)
    assert settings.command_allowed(config, 202, feature)
    assert settings.broadcast_allowed(config, 202, feature)
    assert settings.command_allowed(config, None, feature)
    settings.update_group_settings(101, config, commands={feature: {"enabled": True}},
                                   **{section: {feature: {"enabled": False}}})
    assert settings.command_allowed(config, 101, feature)
    assert not settings.broadcast_allowed(config, 101, feature)
    settings.update_group_settings(101, config, features={feature: {"enabled": False}},
                                   **{section: {feature: {"enabled": True}}})
    assert not settings.command_allowed(config, 101, feature)
    assert not settings.broadcast_allowed(config, 101, feature)
    settings.reset_group_settings(101, config)
    assert settings.command_allowed(config, 101, feature)
    assert settings.broadcast_allowed(config, 101, feature)
    assert groups["101"].config == {"unrelated": {"enabled": True}}
    assert not settings.command_allowed(config, 303, feature)
    assert not settings.broadcast_allowed(config, 303, feature)
    settings.update_group_settings(101, config, enabled=False)
    assert not settings.command_allowed(config, 101, feature)
    assert not settings.broadcast_allowed(config, 101, feature)
    disabled = config.model_copy(update={f"sixty_api_{feature}_enabled": False})
    assert not settings.command_allowed(disabled, 202, feature)
    assert not settings.broadcast_allowed(disabled, 202, feature)


@pytest.mark.parametrize("feature,section,flag", [
    ("world", "push", "sixty_api_world_push_enabled"),
    ("fabing", "random_push", "sixty_api_fabing_random_push_enabled"),
])
def test_sending_respects_independent_switches_and_stale_jobs(monkeypatch, feature, section, flag):
    settings, scheduler, Config = _modules()
    _memory_groups(monkeypatch, settings)
    from src.nonebot_plugins.liteyuki_60s import commands
    from src.nonebot_plugins.liteyuki_60s.service import Content

    config = Config(sixty_api_group_ids=[101, 202], sixty_api_push_interval_seconds=0, **{flag: True})
    settings.update_group_settings(101, config, commands={feature: {"enabled": False}})
    settings.update_group_settings(202, config, **{section: {feature: {"enabled": False}}})
    calls, sent = [], []

    class Finished(Exception): pass

    class Matcher:
        _liteyuki_group_id = 101
        async def finish(self, message): raise Finished(message)
        async def send(self, message): sent.append(message)

    class Bot:
        async def send_group_msg(self, *, group_id, message): sent.append(group_id)

    async def fetch(*args, **kwargs):
        calls.append(args)
        return Content("text", "sample")

    monkeypatch.setattr(commands, "fetch_content", fetch)
    monkeypatch.setattr(scheduler, "fetch_content", fetch)
    monkeypatch.setattr(scheduler, "choose_push_bot", lambda _: Bot())
    with pytest.raises(Finished, match="手动命令已关闭"):
        asyncio.run(commands._send_feature(Matcher(), feature, config))
    assert calls == []
    assert asyncio.run(scheduler.push_content(config, feature, per_group_random=feature == "fabing"))
    assert sent == [101]
    # A queued job cannot send after the group's broadcast switch is disabled.
    settings.update_group_settings(101, config, **{section: {feature: {"enabled": False}}})
    calls.clear()
    assert not asyncio.run(scheduler.push_content(config, feature, target_group_id=101))
    assert calls == []
    matcher = Matcher()
    matcher._liteyuki_group_id = 202
    asyncio.run(commands._send_feature(matcher, feature, config))
    assert sent == [101, "sample"]
    settings.update_group_settings(101, config, **{section: {feature: {"enabled": True}}})

    async def disable_during_fetch(*args, **kwargs):
        settings.update_group_settings(101, config, **{section: {feature: {"enabled": False}}})
        return Content("text", "late result")

    monkeypatch.setattr(scheduler, "fetch_content", disable_during_fetch)
    assert not asyncio.run(scheduler.push_content(config, feature, target_group_id=101,
                                                  per_group_random=feature == "fabing"))
    assert sent == [101, "sample"]


def test_management_commands_persist_switches_and_reschedule_only_current_group(monkeypatch):
    settings, scheduler, Config = _modules()
    _memory_groups(monkeypatch, settings)
    from src.nonebot_plugins import liteyuki_60s
    from src.nonebot_plugins.liteyuki_60s import commands

    config = Config(sixty_api_group_ids=[101, 202])
    monkeypatch.setattr(liteyuki_60s, "config", config)
    rescheduled = []
    monkeypatch.setattr(scheduler, "reschedule_group", lambda _, gid: rescheduled.append(gid))

    class Finished(Exception): pass
    class Matcher:
        async def finish(self, message): raise Finished(message)

    def manage(*args):
        with pytest.raises(Finished, match="已更新"):
            asyncio.run(commands.handle_sixty_admin(SimpleNamespace(main_args={"raw": args}),
                         SimpleNamespace(group_id=101), None, Matcher()))

    manage("命令", "发病语录", "关")
    manage("播报", "发病语录播报", "开")
    assert not settings.command_allowed(config, 101, "fabing")
    assert settings.broadcast_allowed(config, 101, "fabing")
    assert settings.command_allowed(config, 202, "fabing")
    assert not settings.broadcast_allowed(config, 202, "fabing")
    manage("播报", "摸鱼日报", "开")
    assert settings.broadcast_allowed(config, 101, "moyu")
    assert rescheduled == [101, 101, 101]
    status = commands._status("101", config)
    assert "手动命令：" in status and "发病文学关（群级覆盖）" in status
    assert "发病文学：开" in status
