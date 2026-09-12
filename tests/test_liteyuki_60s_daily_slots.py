from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import nonebot
import pytest


@pytest.fixture(scope="module")
def scheduler_module():
    if "src.utils" not in sys.modules:
        package = types.ModuleType("src.utils")
        package.__path__ = [str(Path("src/utils").resolve())]
        sys.modules["src.utils"] = package
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_60s import scheduler

    return scheduler


class FakeJob:
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
        self.jobs[id] = FakeJob(id, func, kwargs)


def daily_config(**values):
    from src.nonebot_plugins.liteyuki_60s.config import SixtyApiConfig

    defaults = {
        "sixty_api_random_push_mode": "daily_slots",
        "sixty_api_fabing_random_push_enabled": True,
        "sixty_api_dad_joke_random_push_enabled": True,
        "sixty_api_random_startup_grace_minutes": 0,
    }
    defaults.update(values)
    return SixtyApiConfig(**defaults)


def use_store(monkeypatch, scheduler_module, path):
    from src.nonebot_plugins.liteyuki_60s.state import RandomPushPlanStore

    store = RandomPushPlanStore(path)
    monkeypatch.setattr(scheduler_module, "random_push_plan_store", store)
    return store


def test_daily_range_validation(scheduler_module) -> None:
    from pydantic import ValidationError
    from src.nonebot_plugins.liteyuki_60s.config import SixtyApiConfig

    with pytest.raises(ValidationError):
        SixtyApiConfig(sixty_api_fabing_random_daily_min=3, sixty_api_fabing_random_daily_max=2)


def test_interval_mode_keeps_single_next_run_job(monkeypatch, scheduler_module) -> None:
    from src.nonebot_plugins.liteyuki_60s.config import SixtyApiConfig

    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(scheduler_module, "scheduler", fake_scheduler)
    monkeypatch.setattr(scheduler_module, "next_random_time", lambda *_args: datetime(2026, 5, 1, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    monkeypatch.setattr(scheduler_module.random, "randint", lambda *_args: 1)
    config = SixtyApiConfig(
        sixty_api_group_ids=[101],
        sixty_api_fabing_random_push_enabled=True,
    )
    scheduler_module._schedule_random(config, "fabing")
    assert set(fake_scheduler.jobs) == {"liteyuki_60s.fabing_random.101"}


def test_daily_slots_are_per_group_bounded_and_persisted(monkeypatch, tmp_path, scheduler_module) -> None:
    store = use_store(monkeypatch, scheduler_module, tmp_path / "plans.json")
    config = daily_config(
        sixty_api_fabing_random_daily_min=2,
        sixty_api_fabing_random_daily_max=2,
        sixty_api_fabing_random_start="08:00",
        sixty_api_fabing_random_end="12:00",
        sixty_api_random_edge_padding_minutes=20,
    )
    now = datetime(2026, 5, 1, 7, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    day, first, _ = scheduler_module._daily_plan(config, "fabing", 101, now)
    _, second, _ = scheduler_module._daily_plan(config, "fabing", 202, now)
    assert day == "2026-05-01"
    assert len(first) == len(second) == 2
    assert all(datetime(2026, 5, 1, 8, 20, tzinfo=now.tzinfo) <= value <= datetime(2026, 5, 1, 11, 40, tzinfo=now.tzinfo) for value in first + second)
    assert store.get(day, 101, "fabing") is not None
    assert store.get(day, 202, "fabing") is not None


def test_daily_slots_share_group_cooldown(monkeypatch, tmp_path, scheduler_module) -> None:
    use_store(monkeypatch, scheduler_module, tmp_path / "plans.json")
    config = daily_config(
        sixty_api_fabing_random_daily_min=2,
        sixty_api_fabing_random_daily_max=2,
        sixty_api_dad_joke_random_daily_min=2,
        sixty_api_dad_joke_random_daily_max=2,
        sixty_api_random_global_cooldown_minutes=90,
        sixty_api_fabing_random_start="08:00",
        sixty_api_fabing_random_end="22:00",
        sixty_api_dad_joke_random_start="08:00",
        sixty_api_dad_joke_random_end="22:00",
    )
    now = datetime(2026, 5, 1, 7, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    _, fabing, _ = scheduler_module._daily_plan(config, "fabing", 101, now)
    _, jokes, _ = scheduler_module._daily_plan(config, "dad_joke", 101, now)
    assert fabing and jokes
    assert all(abs(left - right).total_seconds() >= 90 * 60 for left in fabing for right in jokes)


def test_daily_slots_restore_sent_slots_after_reload(monkeypatch, tmp_path, scheduler_module) -> None:
    path = tmp_path / "plans.json"
    store = use_store(monkeypatch, scheduler_module, path)
    config = daily_config(sixty_api_fabing_random_daily_min=1, sixty_api_fabing_random_daily_max=1)
    now = datetime(2026, 5, 1, 7, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    day, scheduled, _ = scheduler_module._daily_plan(config, "fabing", 101, now)
    store.mark_sent(day, 101, "fabing", scheduled[0].isoformat())
    reloaded = use_store(monkeypatch, scheduler_module, path)
    _, restored, sent = scheduler_module._daily_plan(config, "fabing", 101, now)
    assert restored == scheduled
    assert scheduled[0].isoformat() in sent
    assert reloaded.get(day, 101, "fabing")["sent_times"] == [scheduled[0].isoformat()]


def test_daily_slots_tiny_window_degrades_without_loop(monkeypatch, tmp_path, scheduler_module) -> None:
    use_store(monkeypatch, scheduler_module, tmp_path / "plans.json")
    config = daily_config(
        sixty_api_fabing_random_start="08:00",
        sixty_api_fabing_random_end="08:10",
        sixty_api_random_edge_padding_minutes=20,
    )
    _, scheduled, _ = scheduler_module._daily_plan(
        config, "fabing", 101, datetime(2026, 5, 1, 7, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    )
    assert scheduled == []


def test_blacklist_initializes_random_jobs_after_connect(monkeypatch, tmp_path, scheduler_module) -> None:
    use_store(monkeypatch, scheduler_module, tmp_path / "plans.json")
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(scheduler_module, "scheduler", fake_scheduler)
    config = daily_config(
        sixty_api_group_mode="blacklist",
        sixty_api_fabing_random_push_enabled=True,
        sixty_api_dad_joke_random_push_enabled=False,
    )

    class Bot:
        self_id = "1"

        async def get_group_list(self):
            return [{"group_id": 101}, {"group_id": 202}]

    bot = Bot()
    monkeypatch.setattr(scheduler_module.nonebot, "get_bots", lambda: {"1": bot})
    asyncio.run(scheduler_module.initialize_random_pushes_after_connect(config, bot))
    job_ids = set(fake_scheduler.jobs)
    assert any(job_id.startswith("liteyuki_60s.fabing_random.101.") for job_id in job_ids)
    assert any(job_id.startswith("liteyuki_60s.fabing_random.202.") for job_id in job_ids)
    asyncio.run(scheduler_module.initialize_random_pushes_after_connect(config, bot))
    assert set(fake_scheduler.jobs) == job_ids


def test_corrupt_daily_plan_state_falls_back_to_empty(tmp_path, scheduler_module) -> None:
    from src.nonebot_plugins.liteyuki_60s.state import RandomPushPlanStore

    path = tmp_path / "plans.json"
    path.write_text("not json", encoding="utf-8")
    store = RandomPushPlanStore(path)
    assert store.get("2026-05-01", 101, "fabing") is None
