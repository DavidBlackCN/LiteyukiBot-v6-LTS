import asyncio

import nonebot
from src.nonebot_plugins.liteyuki_bilibili.models import (
    BilibiliEvent,
    BilibiliLiveStatus,
    BilibiliVideo,
)
from src.nonebot_plugins.liteyuki_bilibili.config import BilibiliConfig
from src.nonebot_plugins.liteyuki_bilibili.scheduler import SubscriptionPoller
from src.nonebot_plugins.liteyuki_bilibili.storage import SubscriptionStore


class FakeClient:
    def __init__(self) -> None:
        self.dynamic_calls = 0
        self.video_calls = 0
        self.live_calls = 0
        self.dynamics = [BilibiliEvent(kind="dynamic", uid="42", event_id="dynamic-old")]
        self.videos = [BilibiliVideo(bvid="BV-old", author_uid="42")]
        self.live = BilibiliLiveStatus(uid="42", room_id="100", live=False)

    async def get_latest_dynamics(self, uid: str):
        self.dynamic_calls += 1
        return self.dynamics

    async def get_latest_videos(self, uid: str):
        self.video_calls += 1
        return self.videos

    async def get_live_status(self, uid: str):
        self.live_calls += 1
        return self.live


def test_first_poll_only_sets_baseline_and_later_fans_out_per_target(tmp_path) -> None:
    async def scenario() -> None:
        store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
        for target in ("ok", "fails"):
            store.add(target_type="group", target_id=target, uid="42")
        client = FakeClient()
        delivered: list[tuple[str, str]] = []

        async def send(subscription, event) -> bool:
            delivered.append((subscription.target_id, event.event_id))
            return subscription.target_id == "ok"

        poller = SubscriptionPoller(client, store, send)
        assert (await poller.poll()).delivered_count == 0
        assert not delivered
        client.dynamics = [
            BilibiliEvent(kind="dynamic", uid="42", event_id="dynamic-new"),
            BilibiliEvent(kind="dynamic", uid="42", event_id="dynamic-old"),
        ]
        result = await poller.poll()
        assert result.uid_count == 1
        assert result.delivered_count == 1 and result.failed_deliveries == 1
        assert client.dynamic_calls == client.video_calls == client.live_calls == 2
        assert store.get("group", "ok", "42").last_dynamic_id == "dynamic-new"
        assert store.get("group", "fails", "42").last_dynamic_id == "dynamic-old"

    asyncio.run(scenario())


def test_live_transitions_and_feature_errors_are_isolated(tmp_path) -> None:
    async def scenario() -> None:
        store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
        store.add(target_type="group", target_id="one", uid="42")
        client = FakeClient()
        sent: list[str] = []

        async def send(_subscription, event) -> bool:
            sent.append(event.kind)
            return True

        poller = SubscriptionPoller(client, store, send)
        await poller.poll()
        client.live = BilibiliLiveStatus(uid="42", room_id="100", title="开播", live=True)
        await poller.poll()
        client.live = BilibiliLiveStatus(uid="42", room_id="100", title="下播", live=False)
        await poller.poll()
        assert sent == ["live_start", "live_end"]

    asyncio.run(scenario())


def test_runtime_registers_one_coalesced_job(monkeypatch) -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_bilibili import runtime

    class FakeScheduler:
        def __init__(self) -> None:
            self.jobs = {}

        def get_job(self, job_id):
            return self.jobs.get(job_id)

        def remove_job(self, job_id) -> None:
            self.jobs.pop(job_id, None)

        def add_job(self, function, trigger, *, id, **kwargs) -> None:
            self.jobs[id] = (function, trigger, kwargs)

    class FakeClient:
        def __init__(self, *_args) -> None:
            pass

        async def start(self) -> None:
            pass

    class FakePoller:
        def __init__(self, *_args) -> None:
            pass

        async def poll(self):
            raise AssertionError("the scheduled function is not executed during registration")

    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(runtime, "scheduler", fake_scheduler)
    monkeypatch.setattr(runtime, "CredentialManager", lambda *_args: object())
    monkeypatch.setattr(runtime, "BilibiliClient", FakeClient)
    monkeypatch.setattr(runtime, "SubscriptionStore", lambda: object())
    monkeypatch.setattr(runtime, "SubscriptionPoller", FakePoller)

    runtime.configure_jobs(BilibiliConfig(bilibili_poll_interval=30))
    _, trigger, options = fake_scheduler.jobs[runtime.JOB_ID]
    assert trigger == "interval"
    assert options["seconds"] == 30
    assert options["max_instances"] == 1 and options["coalesce"] is True
    runtime.configure_jobs(BilibiliConfig(bilibili_push_enabled=False))
    assert runtime.JOB_ID not in fake_scheduler.jobs
