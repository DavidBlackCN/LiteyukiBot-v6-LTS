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


@pytest.mark.parametrize("global_prefix", [True, False])
def test_onebot_dispatch_notifies_and_accepts_notification_commands(tmp_path, global_prefix):
    from test_issue_90_htmlrender import _run_python

    _run_python(
        """
        import asyncio
        import itertools
        import os
        import nonebot
        from nonebot.adapters.onebot.v11 import Adapter, Bot, FriendRequestEvent, PrivateMessageEvent
        from nonebot.message import handle_event

        nonebot.init(superusers={"99"}, command_start={"/"},
                     alconna_use_command_start=os.environ["FRIEND_GLOBAL_PREFIX"] == "True")
        driver = nonebot.get_driver()
        driver.register_adapter(Adapter)
        assert nonebot.load_plugin("src.nonebot_plugins.liteyuki_friend_request")
        from src.nonebot_plugins.liteyuki_friend_request import commands
        from src.nonebot_plugins.liteyuki_friend_request.service import FriendRequestService, FriendRequestStore

        service = FriendRequestService(FriendRequestStore(os.environ["FRIEND_TEST_DB"]))
        commands.default_service = service
        bot = Bot(driver._adapters["OneBot V11"], "10000")
        calls = []
        async def api(name, **data):
            calls.append((name, data))
            return {"message_id": len(calls)}
        bot.call_api = api
        nonebot.get_bot = lambda bot_id: bot if bot_id == "10000" else None

        message_ids = itertools.count(10)
        def message(text, user=99):
            return PrivateMessageEvent(time=1, self_id=10000, post_type="message", message_type="private",
                sub_type="friend", message_id=next(message_ids), user_id=user, message=text,
                original_message=text, raw_message=text, font=0, sender={"user_id": user})

        async def run():
            for flag in ("first", "first", "second", "third"):
                event = FriendRequestEvent(time=1, self_id=10000, post_type="request",
                    request_type="friend", user_id=123, comment="test", flag=flag)
                await handle_event(bot, event)
            notifications = [data for name, data in calls if name == "send_private_msg"]
            assert len(notifications) == 3
            assert all(data["user_id"] == 99 for data in notifications)
            assert "/好友同意 1" in notifications[0]["message"]
            await handle_event(bot, message("/好友同意 1", user=123))
            assert service.store.get(1).status == "pending"
            await handle_event(bot, message("/好友同意 1 测试备注"))
            await handle_event(bot, message("/好友拒绝 2"))
            await handle_event(bot, message("/好友申请列表"))
            reviews = [data for name, data in calls if name == "set_friend_add_request"]
            assert reviews == [{"flag": "first", "approve": True, "remark": "测试备注"},
                               {"flag": "second", "approve": False}]
            assert service.store.get(1).status == "approved"
            assert service.store.get(2).status == "rejected"
            assert service.store.get(3).status == "pending"
            assert any("#3" in str(data.get("message")) and "待处理" in str(data.get("message"))
                       for name, data in calls if name == "send_msg")
        try:
            asyncio.run(run())
        finally:
            service.store.db.conn.close()
        """,
        FRIEND_TEST_DB=str(tmp_path / "requests.ldb"),
        FRIEND_GLOBAL_PREFIX=str(global_prefix),
    )
