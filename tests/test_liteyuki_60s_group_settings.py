from __future__ import annotations

from types import SimpleNamespace

import nonebot


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
