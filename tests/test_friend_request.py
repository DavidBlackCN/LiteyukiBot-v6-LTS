import asyncio
from pathlib import Path
from types import SimpleNamespace

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import FriendRequestEvent


try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(superusers={"99"})

from src.nonebot_plugins.liteyuki_friend_request.model import FriendRequest
from src.nonebot_plugins.liteyuki_friend_request.service import (
    APPROVED,
    PENDING,
    REJECTED,
    FriendRequestService,
    FriendRequestStore,
)


class NotifyBot:
    def __init__(self, superusers=("1", "2"), fail_for=()) -> None:
        self.self_id = "10000"
        self.config = SimpleNamespace(superusers=set(superusers))
        self.fail_for = {int(value) for value in fail_for}
        self.sent = []

    async def send_private_msg(self, *, user_id, message):
        if user_id in self.fail_for:
            raise RuntimeError("send failed")
        self.sent.append((user_id, message))


class ReviewBot:
    def __init__(self, fail=False) -> None:
        self.fail = fail
        self.calls = []

    async def set_friend_add_request(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("API failed")


def make_service(path: Path) -> FriendRequestService:
    return FriendRequestService(FriendRequestStore(path))


def event(flag="flag-1", *, bot_id="10000", user_id=123456, comment="你好", time=1_789_000_000):
    return FriendRequestEvent(
        time=time,
        self_id=int(bot_id),
        post_type="request",
        request_type="friend",
        user_id=user_id,
        comment=comment,
        flag=flag,
    )


def test_friend_event_creates_pending_once_and_notifies_all_superusers(tmp_path):
    service = make_service(tmp_path / "requests.ldb")
    bot = NotifyBot()

    request = asyncio.run(service.receive(bot, event()))
    duplicate = asyncio.run(service.receive(bot, event()))

    assert request.request_id == 1
    assert (request.bot_id, request.user_id, request.comment, request.flag, request.status) == (
        "10000", "123456", "你好", "flag-1", PENDING,
    )
    assert duplicate.request_id == request.request_id
    assert [user_id for user_id, _ in bot.sent] == [1, 2] or [user_id for user_id, _ in bot.sent] == [2, 1]
    assert len(bot.sent) == 2
    assert "#1" in bot.sent[0][1]


def test_notification_failure_does_not_block_other_superusers(tmp_path):
    service = make_service(tmp_path / "requests.ldb")
    bot = NotifyBot(fail_for={1})

    asyncio.run(service.receive(bot, event()))

    assert [user_id for user_id, _ in bot.sent] == [2]


def test_pending_list_hides_handled_requests(tmp_path):
    from src.nonebot_plugins.liteyuki_friend_request.commands import pending_text

    store = FriendRequestStore(tmp_path / "requests.ldb")
    pending, _ = store.create(bot_id="1", user_id="11", comment="pending", flag="a", created_at="2026-01-01 00:00:00")
    handled, _ = store.create(bot_id="1", user_id="12", comment="hidden", flag="b", created_at="2026-01-01 00:00:00")
    store.mark_handled(store.get(handled.request_id), APPROVED, "99")

    text = pending_text(store.pending())

    assert f"#{pending.request_id}" in text
    assert "hidden" not in text
    assert "当前没有" in pending_text([])


def test_approve_calls_original_bot_and_persists_success(monkeypatch, tmp_path):
    import src.nonebot_plugins.liteyuki_friend_request.service as service_module

    service = make_service(tmp_path / "requests.ldb")
    request, _ = service.store.create(bot_id="20000", user_id="123", comment="hi", flag="v11-flag", created_at="2026-01-01 00:00:00")
    bot = ReviewBot()
    monkeypatch.setattr(service_module.nonebot, "get_bot", lambda bot_id: bot)

    outcome = asyncio.run(service.review(request.request_id, True, "99", "张三"))

    assert outcome.kind == "success"
    assert bot.calls == [{"flag": "v11-flag", "approve": True, "remark": "张三"}]
    saved = service.store.get(request.request_id)
    assert saved.status == APPROVED and saved.handled_by == "99" and saved.handled_at


def test_reject_calls_api_without_remark_and_persists_success(monkeypatch, tmp_path):
    import src.nonebot_plugins.liteyuki_friend_request.service as service_module

    service = make_service(tmp_path / "requests.ldb")
    request, _ = service.store.create(bot_id="20000", user_id="123", comment="hi", flag="v11-flag", created_at="2026-01-01 00:00:00")
    bot = ReviewBot()
    monkeypatch.setattr(service_module.nonebot, "get_bot", lambda bot_id: bot)

    outcome = asyncio.run(service.review(request.request_id, False, "99"))

    assert outcome.kind == "success"
    assert bot.calls == [{"flag": "v11-flag", "approve": False}]
    assert service.store.get(request.request_id).status == REJECTED


def test_api_failure_and_offline_bot_keep_request_pending(monkeypatch, tmp_path):
    import src.nonebot_plugins.liteyuki_friend_request.service as service_module

    service = make_service(tmp_path / "requests.ldb")
    failed, _ = service.store.create(bot_id="20000", user_id="123", comment="hi", flag="bad", created_at="2026-01-01 00:00:00")
    offline, _ = service.store.create(bot_id="30000", user_id="124", comment="hi", flag="offline", created_at="2026-01-01 00:00:00")
    monkeypatch.setattr(service_module.nonebot, "get_bot", lambda bot_id: ReviewBot(fail=True) if bot_id == "20000" else (_ for _ in ()).throw(KeyError(bot_id)))

    assert asyncio.run(service.review(failed.request_id, True, "99")).kind == "failed"
    assert asyncio.run(service.review(offline.request_id, True, "99")).kind == "offline"
    assert service.store.get(failed.request_id).status == PENDING
    assert service.store.get(offline.request_id).status == PENDING


def test_handled_request_cannot_be_reviewed_twice(monkeypatch, tmp_path):
    import src.nonebot_plugins.liteyuki_friend_request.service as service_module

    service = make_service(tmp_path / "requests.ldb")
    request, _ = service.store.create(bot_id="20000", user_id="123", comment="hi", flag="once", created_at="2026-01-01 00:00:00")
    bot = ReviewBot()
    monkeypatch.setattr(service_module.nonebot, "get_bot", lambda _: bot)

    assert asyncio.run(service.review(request.request_id, True, "99")).kind == "success"
    assert asyncio.run(service.review(request.request_id, False, "98")).kind == "handled"
    assert len(bot.calls) == 1


def test_pending_request_survives_store_reload(tmp_path):
    path = tmp_path / "requests.ldb"
    original = FriendRequestStore(path)
    request, _ = original.create(bot_id="100", user_id="200", comment="reload", flag="persist", created_at="2026-01-01 00:00:00")

    reloaded = FriendRequestStore(path)

    assert reloaded.get(request.request_id).status == PENDING


def test_commands_are_superuser_only_and_refuse_group_messages():
    from src.nonebot_plugins.liteyuki_friend_request import commands
    from nonebot.permission import SUPERUSER

    class Matcher:
        message = ""

        async def finish(self, message):
            self.message = message

    matcher = Matcher()
    asyncio.run(commands._private_or_finish(SimpleNamespace(group_id=1), matcher))

    assert "Superuser" in repr(commands.request_list.permission)
    assert "Superuser" in repr(commands.approve_request.permission)
    assert "Superuser" in repr(commands.reject_request.permission)
    assert matcher.message == "请私聊 Bot 处理好友申请。"
