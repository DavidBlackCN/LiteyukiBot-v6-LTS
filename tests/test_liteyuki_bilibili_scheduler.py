import asyncio

import nonebot
from src.nonebot_plugins.liteyuki_bilibili.models import (
    BilibiliEvent,
    BilibiliLiveStatus,
    BilibiliUser,
    BilibiliVideo,
)
from src.nonebot_plugins.liteyuki_bilibili.config import BilibiliConfig
from src.nonebot_plugins.liteyuki_bilibili.scheduler import PollResult, SubscriptionPoller
from src.nonebot_plugins.liteyuki_bilibili.storage import SubscriptionStore


class FakeClient:
    def __init__(self) -> None:
        self.dynamic_calls = 0
        self.video_calls = 0
        self.live_calls = 0
        self.user_calls = 0
        self.dynamics = [BilibiliEvent(kind="dynamic", uid="42", event_id="100")]
        self.videos = [BilibiliVideo(bvid="BV-old", author_uid="42")]
        self.live = BilibiliLiveStatus(uid="42", room_id="100", live=False)
        self.user = BilibiliUser(uid="42", name="UP", avatar_url="https://i0.hdslb.com/up.jpg")
        self.user_error: Exception | None = None

    async def get_latest_dynamics(self, uid: str):
        self.dynamic_calls += 1
        return self.dynamics

    async def get_latest_videos(self, uid: str):
        self.video_calls += 1
        return self.videos

    async def get_live_status(self, uid: str):
        self.live_calls += 1
        return self.live

    async def get_user_info(self, uid: str):
        self.user_calls += 1
        if self.user_error:
            raise self.user_error
        return self.user


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
            BilibiliEvent(kind="dynamic", uid="42", event_id="101"),
            BilibiliEvent(kind="dynamic", uid="42", event_id="100"),
        ]
        result = await poller.poll()
        assert result.uid_count == 1
        assert result.delivered_count == 1 and result.failed_deliveries == 1
        assert client.dynamic_calls == client.video_calls == client.live_calls == 2
        assert store.get("group", "ok", "42").last_dynamic_id == "101"
        assert store.get("group", "fails", "42").last_dynamic_id == "100"

    asyncio.run(scenario())


def test_live_transitions_and_feature_errors_are_isolated(tmp_path) -> None:
    async def scenario() -> None:
        store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
        store.add(target_type="group", target_id="one", uid="42")
        client = FakeClient()
        sent: list[BilibiliEvent] = []

        async def send(_subscription, event) -> bool:
            sent.append(event)
            return True

        poller = SubscriptionPoller(client, store, send)
        await poller.poll()
        client.live = BilibiliLiveStatus(
            uid="42", room_id="100", title="开播", area_name="游戏", cover_url="cover", live=True,
            url="https://live.bilibili.com/100",
        )
        await poller.poll()
        client.live = BilibiliLiveStatus(uid="42", room_id="100", title="下播", live=False)
        await poller.poll()
        assert [event.kind for event in sent] == ["live_start", "live_end"]
        assert sent[0].author_name == "UP"
        assert sent[0].avatar_url == "https://i0.hdslb.com/up.jpg"
        assert sent[0].cover_urls == ["cover"] and sent[0].metrics == {"area": "游戏"}
        assert sent[0].url == "https://live.bilibili.com/100" and sent[0].timestamp is not None
        assert client.user_calls == 2

    asyncio.run(scenario())


def test_dynamic_baseline_uses_highest_id_even_when_first_item_is_pinned(tmp_path) -> None:
    async def scenario() -> None:
        store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
        store.add(target_type="group", target_id="one", uid="42", video_enabled=False, live_enabled=False)
        client = FakeClient()
        client.dynamics = [
            BilibiliEvent(kind="dynamic", uid="42", event_id="100"),
            BilibiliEvent(kind="dynamic", uid="42", event_id="300"),
            BilibiliEvent(kind="dynamic", uid="42", event_id="200"),
        ]
        poller = SubscriptionPoller(client, store, lambda *_args: None)
        await poller.poll()
        assert store.get("group", "one", "42").last_dynamic_id == "300"

    asyncio.run(scenario())


def test_dynamic_cursor_is_monotonic_and_new_events_are_sent_once(tmp_path) -> None:
    async def scenario() -> None:
        store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
        store.add(target_type="group", target_id="one", uid="42", video_enabled=False, live_enabled=False)
        store.initialize_baseline("group", "one", "42", dynamic_id="200", video_id="BV-old", live_state="offline")
        client = FakeClient()
        client.dynamics = [
            BilibiliEvent(kind="dynamic", uid="42", event_id="202"),
            BilibiliEvent(kind="dynamic", uid="42", event_id="201"),
            BilibiliEvent(kind="dynamic", uid="42", event_id="200"),
        ]
        sent: list[str] = []

        async def send(_subscription, event) -> bool:
            sent.append(event.event_id)
            return True

        poller = SubscriptionPoller(client, store, send)
        await poller.poll()
        await poller.poll()
        client.dynamics = [BilibiliEvent(kind="dynamic", uid="42", event_id="199")]
        await poller.poll()
        assert sent == ["201", "202"]
        assert store.get("group", "one", "42").last_dynamic_id == "202"

    asyncio.run(scenario())


def test_missing_dynamic_or_video_cursor_rebases_without_replaying_history(tmp_path) -> None:
    async def scenario() -> None:
        store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
        store.add(target_type="group", target_id="one", uid="42", live_enabled=False)
        store.initialize_baseline("group", "one", "42", dynamic_id="legacy", video_id="BV-old", live_state="offline")
        client = FakeClient()
        client.dynamics = [
            BilibiliEvent(kind="dynamic", uid="42", event_id="220"),
            BilibiliEvent(kind="dynamic", uid="42", event_id="210"),
        ]
        client.videos = [BilibiliVideo(bvid="BV-new", author_uid="42"), BilibiliVideo(bvid="BV-history", author_uid="42")]
        sent: list[str] = []

        async def send(_subscription, event) -> bool:
            sent.append(event.event_id)
            return True

        await SubscriptionPoller(client, store, send).poll()
        subscription = store.get("group", "one", "42")
        assert not sent
        assert subscription.last_dynamic_id == "220"
        assert subscription.last_video_id == "BV-new"

    asyncio.run(scenario())


def test_numeric_dynamic_cursor_missing_from_page_never_replays_old_items(tmp_path) -> None:
    async def scenario() -> None:
        store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
        store.add(target_type="group", target_id="one", uid="42", video_enabled=False, live_enabled=False)
        store.initialize_baseline("group", "one", "42", dynamic_id="999", video_id="BV-old", live_state="offline")
        client = FakeClient()
        client.dynamics = [
            BilibiliEvent(kind="dynamic", uid="42", event_id="300"),
            BilibiliEvent(kind="dynamic", uid="42", event_id="200"),
        ]
        sent: list[str] = []

        async def send(_subscription, event) -> bool:
            sent.append(event.event_id)
            return True

        await SubscriptionPoller(client, store, send).poll()
        assert not sent
        assert store.get("group", "one", "42").last_dynamic_id == "999"

    asyncio.run(scenario())


def test_live_push_falls_back_to_uid_when_up_lookup_fails(tmp_path) -> None:
    async def scenario() -> None:
        store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
        store.add(target_type="group", target_id="one", uid="42", dynamic_enabled=False, video_enabled=False)
        client = FakeClient()
        sent: list[BilibiliEvent] = []

        async def send(_subscription, event) -> bool:
            sent.append(event)
            return True

        poller = SubscriptionPoller(client, store, send)
        await poller.poll()
        client.user_error = RuntimeError("unavailable")
        client.live = BilibiliLiveStatus(uid="42", room_id="100", title="开播", live=True)
        await poller.poll()
        assert sent[0].kind == "live_start"
        assert sent[0].author_name == "UP 42" and sent[0].avatar_url == ""

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


def test_poll_result_logging_avoids_info_for_empty_polls(monkeypatch) -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_bilibili import runtime

    messages: list[tuple[str, str]] = []
    for level in ("debug", "info", "warning"):
        monkeypatch.setattr(runtime.logger, level, lambda message, level=level: messages.append((level, message)))

    runtime._log_poll_result(PollResult(uid_count=1))
    assert messages == [("debug", "Bilibili 轮询完成: uid=1 delivered=0 failed=0")]
    runtime._log_poll_result(PollResult(uid_count=1, delivered_count=1))
    runtime._log_poll_result(PollResult(uid_count=1, failed_deliveries=1))
    assert messages[1] == ("info", "Bilibili 推送完成: delivered=1")
    assert messages[2] == ("warning", "Bilibili 轮询完成: uid=1 delivered=0 failed=1")
