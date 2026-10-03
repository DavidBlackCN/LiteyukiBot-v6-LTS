from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from test_liteyuki_twitter_parser import modules


def state(tmp_path):
    _, Config, Post, _ = modules()
    from src.nonebot_plugins.liteyuki_twitter.storage import TwitterStore
    from src.nonebot_plugins.liteyuki_twitter.config import FollowOptions
    return Config, Post, TwitterStore(str(tmp_path / "twitter.ldb")), FollowOptions


def test_subscription_overrides_persist_reset_and_group_isolation(tmp_path):
    Config, _, store, Follow = state(tmp_path)
    config = Config(twitter_group_ids=[101, 202], twitter_follows=["example"], twitter_group_follows={202: ["other"]})
    assert set(store.follows(config, "101")) == {"example"}
    assert set(store.follows(config, "202")) == {"other"}
    store.unfollow("101", "@Example")
    store.follow("101", Follow(account="new", media_only=True))
    reloaded = type(store)(store.path)
    assert set(reloaded.follows(config, "101")) == {"new"}
    assert reloaded.follows(config, "101")["new"][0].media_only
    assert set(reloaded.follows(config, "202")) == {"other"}
    reloaded.reset("101")
    assert set(reloaded.follows(config, "101")) == {"example"}


def test_group_switches_are_independent_and_preserve_other_config(monkeypatch):
    _, Config, _, _ = modules()
    from src.nonebot_plugins.liteyuki_twitter import group_settings as groups
    saved = {}
    model = SimpleNamespace(config={"other": {"enabled": True}})
    class DB:
        def save(self, item): saved.update(item.config)
    monkeypatch.setattr(groups, "group_model", lambda _: (DB(), model))
    config = Config(twitter_enabled=True, twitter_group_ids=[101])
    groups.update(config, "101", commands=False)
    assert not groups.locally_allowed(config, "101", "commands")
    assert groups.locally_allowed(config, "101", "push")
    assert groups.locally_allowed(config, "101", "links")
    groups.update(config, "101", commands=True, push=False)
    assert groups.locally_allowed(config, "101", "commands")
    assert not groups.locally_allowed(config, "101", "push")
    assert not groups.locally_allowed(config, "202", "commands")
    assert saved["other"] == {"enabled": True}
    assert "provider" not in model.config["liteyuki_twitter"]
    groups.update(config, "101", enabled=False)
    assert not groups.locally_allowed(config, "101", "commands")


def test_baseline_pinned_filters_dedup_and_retries(tmp_path, monkeypatch):
    Config, Post, store, Follow = state(tmp_path)
    from src.nonebot_plugins.liteyuki_twitter import storage
    from src.nonebot_plugins.liteyuki_twitter.models import Media
    clock = [1000.0]
    monkeypatch.setattr(storage.time, "time", lambda: clock[0])
    options = Follow(account="example")
    store.set_active("101", True)
    assert store.ingest("101", options, [Post("100", "example")]) == 0
    clock[0] = 2000
    posts = [Post("101", "example", text="新文"), Post("102", "example", reply=True),
             Post("103", "other", repost=True), Post("99", "example", pinned=True)]
    assert store.ingest("101", options, posts) == 1
    assert store.ingest("101", options, posts) == 0
    row = store.pending("101")[0]
    assert store.pending_count("202") == 0
    store.finish(row, False)
    assert store.pending("101") == []
    for _ in range(2):
        clock[0] += 1000
        row = store.pending("101")[0]
        store.finish(row, False)
    assert store.pending("101") == []
    assert store.ingest("101", options, posts) == 0
    store.set_active("101", False)
    store.set_active("101", True)
    assert store.ingest("101", options, [Post("200", "example")]) == 0
    assert store.pending_count("101") == 0
    media = Follow(account="example", media_only=True, replies=True, reposts=True)
    assert store.ingest("101", media, [Post("201", "example"), Post("202", "example", media=[Media("image")])]) == 1


def test_empty_baseline_expiry_and_batch_limit(tmp_path, monkeypatch):
    _, Post, store, Follow = state(tmp_path)
    from src.nonebot_plugins.liteyuki_twitter import storage
    clock = [1000.0]
    monkeypatch.setattr(storage.time, "time", lambda: clock[0])
    options = Follow(account="example")
    assert store.ingest("101", options, []) == 0
    clock[0] = 2000
    pub = datetime.fromtimestamp(1500, UTC).isoformat()
    assert store.ingest("101", options, [Post(str(i), "example", published_at=pub) for i in range(100, 110)]) == 10
    assert len(store.pending("101")) == 5
    assert store.window_gap("101", "example", [Post("200", "example")])
    clock[0] += 86401
    assert store.pending("101") == []


def test_one_fetch_per_account_failed_target_and_resume(tmp_path):
    Config, Post, store, _ = state(tmp_path)
    from src.nonebot_plugins.liteyuki_twitter.scheduler import TwitterPoller
    config = Config(twitter_enabled=True, twitter_group_ids=[101, 202], twitter_follows=["example"])
    fetched, sent = [], []
    available = {"101": True, "202": True}
    current = [Post("100", "example")]
    class Client:
        async def get_timeline(self, account): fetched.append(account); return current
    async def allowed(group): return available[group]
    async def deliver(group, post, account): sent.append((group, post.post_id)); return group == "202"
    poller = TwitterPoller(config, Client(), store, deliver, can_push=allowed)
    asyncio.run(poller.poll())
    assert fetched == ["example"] and sent == []
    current = [Post("101", "example")]
    result = asyncio.run(poller.poll())
    assert result["sent"] == result["failed"] == 1
    assert len(fetched) == 2 and store.pending_count("101") == 1
    assert store.pending_count("202") == 0
    available["101"] = False
    current = [Post("102", "example")]
    asyncio.run(poller.poll())
    available["101"] = True
    current = [Post("103", "example")]
    asyncio.run(poller.poll())
    assert ("101", "103") not in sent and store.pending_count("101") == 0


def test_failed_fetch_does_not_baseline(tmp_path):
    Config, Post, store, _ = state(tmp_path)
    from src.nonebot_plugins.liteyuki_twitter.scheduler import TwitterPoller
    from src.nonebot_plugins.liteyuki_twitter.models import SourceError
    config = Config(twitter_group_ids=[101], twitter_follows=["example"])
    class Client:
        async def get_timeline(self, account): raise SourceError("失败")
    async def allowed(_): return True
    async def deliver(*_): raise AssertionError("not expected")
    asyncio.run(TwitterPoller(config, Client(), store, deliver, can_push=allowed).poll())
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM baselines").fetchone()[0] == 0


def test_blacklist_poll_targets_and_reentry_baseline(tmp_path):
    Config, Post, store, _ = state(tmp_path)
    from src.nonebot_plugins.liteyuki_twitter.scheduler import TwitterPoller
    config = Config(twitter_enabled=True, twitter_group_mode="blacklist",
                    twitter_group_ids=[202], twitter_follows=["example"])
    current, targets, sent = [Post("100", "example")], ["101", "202"], []
    class Client:
        async def get_timeline(self, account): return current
    async def allowed(group): return True
    async def groups(): return targets
    async def deliver(group, post, account): sent.append((group, post.post_id)); return True
    poller = TwitterPoller(config, Client(), store, deliver, can_push=allowed, target_groups=groups)
    asyncio.run(poller.poll())
    assert store.active_groups() == ["101"]
    current[:] = [Post("101", "example")]
    asyncio.run(poller.poll())
    assert sent == [("101", "101")]
    # A failed group-list request must not reset discovery state.
    targets = None
    asyncio.run(poller.poll())
    assert store.active_groups() == ["101"]
    config.twitter_group_ids = ["101", "202"]
    targets = ["101", "202"]
    asyncio.run(poller.poll())
    assert store.active_groups() == []
    config.twitter_group_ids = ["202"]
    current[:] = [Post("102", "example")]
    asyncio.run(poller.poll())
    assert sent == [("101", "101")]  # Reallowed groups rebaseline without history.
    assert store.ingest("101", config.twitter_follows[0], [Post("100", "example")]) == 0
