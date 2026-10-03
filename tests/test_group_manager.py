import os
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_python(source: str, **extra_env: str) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_group_manager_core_behaviour() -> None:
    _run_python(
        """
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        import nonebot
        from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message

        nonebot.init()
        from src.nonebot_plugins.liteyuki_group_manager.core import (
            ban_member,
            extract_reply_message_id,
            format_notice,
            group_only_error,
            has_management_permission,
            has_owner_permission,
            kick_member,
            parse_duration,
            validate_target,
        )

        assert parse_duration("30s", 600, 2592000) == 30
        assert parse_duration("10m", 600, 2592000) == 600
        assert parse_duration("2h", 600, 2592000) == 7200
        assert parse_duration("1d", 600, 2592000) == 86400
        assert parse_duration("15", 600, 2592000) == 900
        assert parse_duration("", 600, 2592000) == 600
        for invalid in ("tomorrow", "-1m", "31d"):
            try:
                parse_duration(invalid, 600, 2592000)
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid duration accepted: {invalid}")

        assert has_management_permission("admin", False)
        assert has_management_permission("owner", False)
        assert has_management_permission("member", True)
        assert not has_management_permission("member", False)
        assert has_owner_permission("owner", False)
        assert not has_owner_permission("admin", False)
        assert has_owner_permission("member", True)

        assert validate_target(
            actor_role="admin", bot_role="admin", target_role="member",
            is_superuser=False, bot_id=1, target_id=2,
        ) is None
        assert validate_target(
            actor_role="admin", bot_role="admin", target_role="admin",
            is_superuser=False, bot_id=1, target_id=2,
        ) is not None
        assert validate_target(
            actor_role="owner", bot_role="member", target_role="member",
            is_superuser=False, bot_id=1, target_id=2,
        ) is not None
        assert validate_target(
            actor_role="owner", bot_role="owner", target_role="member",
            is_superuser=False, bot_id=1, target_id=1,
        ) is not None

        assert group_only_error(SimpleNamespace()) == "该命令只能在群聊中使用"
        group_event = GroupMessageEvent(
            time=0, self_id=1, post_type="message", sub_type="normal",
            user_id=2, message_type="group", message_id=3, message=Message(),
            original_message=Message(), raw_message="", font=0,
            sender={"role": "admin"}, to_me=False, group_id=10001,
        )
        assert group_only_error(group_event) is None

        reply_event = SimpleNamespace(reply=SimpleNamespace(message_id=42))
        assert extract_reply_message_id(reply_event) == 42
        try:
            extract_reply_message_id(SimpleNamespace(reply=None))
        except ValueError:
            pass
        else:
            raise AssertionError("missing reply accepted")

        assert format_notice(
            "欢迎 {nickname}（{user_id}）加入 {group_id}",
            user_id=2, group_id=10001, nickname="小雪",
        ) == "欢迎 小雪（2）加入 10001"
        assert format_notice(
            "欢迎 {unknown}", user_id=2, group_id=10001,
        ) == "欢迎 {unknown}"
        assert format_notice("错误 {", user_id=2, group_id=10001) == "错误 {"

        async def verify_api_arguments():
            bot = SimpleNamespace(
                set_group_ban=AsyncMock(),
                set_group_kick=AsyncMock(),
            )
            await ban_member(bot, 10001, 2, 600)
            bot.set_group_ban.assert_awaited_once_with(
                group_id=10001, user_id=2, duration=600,
            )
            await kick_member(bot, 10001, 2, True)
            bot.set_group_kick.assert_awaited_once_with(
                group_id=10001, user_id=2, reject_add_request=True,
            )

        asyncio.run(verify_api_arguments())

        from src.nonebot_plugins.liteyuki_group_manager.handlers import (
            _notice_nickname,
            _remember_nickname,
        )

        async def verify_leave_notice_nickname():
            bot = SimpleNamespace(
                self_id="1",
                get_group_member_info=AsyncMock(
                    side_effect=RuntimeError("member already left")
                ),
                get_stranger_info=AsyncMock(return_value={"nickname": "小雪"}),
            )
            assert await _notice_nickname(bot, 10001, 2) == "小雪"
            bot.get_stranger_info.assert_awaited_once_with(
                user_id=2, no_cache=True,
            )

        asyncio.run(verify_leave_notice_nickname())

        async def verify_cached_leave_notice_nickname():
            bot = SimpleNamespace(
                self_id="1",
                get_group_member_info=AsyncMock(
                    side_effect=RuntimeError("member already left")
                ),
                get_stranger_info=AsyncMock(
                    return_value={"nickname": "2"}
                ),
            )
            _remember_nickname(bot, 10001, 2, "小雪")
            assert await _notice_nickname(bot, 10001, 2) == "小雪"
            bot.get_group_member_info.assert_awaited_once_with(
                group_id=10001, user_id=2, no_cache=False,
            )
            bot.get_stranger_info.assert_not_awaited()

        asyncio.run(verify_cached_leave_notice_nickname())
        """
    )


def test_group_manager_disabled_registers_no_matchers() -> None:
    _run_python(
        """
        import nonebot

        nonebot.init(group_manager_enabled=False)
        plugin = nonebot.load_plugin(
            "src.nonebot_plugins.liteyuki_group_manager"
        )
        assert plugin is not None
        assert not plugin.matcher
        """
    )


def test_leave_nickname_cache_survives_blocking_matchers_and_silent_members():
    _run_python(
        """
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import nonebot
        from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, Message, GroupDecreaseNoticeEvent, GroupIncreaseNoticeEvent
        from nonebot.message import handle_event

        nonebot.init()
        nonebot.get_driver().register_adapter(Adapter)
        assert nonebot.load_plugin("src.nonebot_plugins.liteyuki_group_manager")
        from src.nonebot_plugins.liteyuki_group_manager import handlers as h
        bot = Bot(Adapter(nonebot.get_driver()), "1")
        blocker = nonebot.on_type(GroupMessageEvent, priority=1, block=True)
        handled = []
        @blocker.handle()
        async def block_message():
            handled.append(True)

        async def scenario():
            h._member_nickname_cache.clear()
            async def connect_api(api, **params):
                if api == "get_group_list":
                    return [{"group_id":10001}]
                if api == "get_group_member_list":
                    return [{"user_id":8,"nickname":"连接时获取的昵称"}]
                raise AssertionError(api)
            bot.call_api = AsyncMock(side_effect=connect_api)
            await h.prime_member_nicknames_on_connect(bot)
            assert h._member_nickname_cache[("1",10001,8)] == "连接时获取的昵称"
            event = GroupMessageEvent(time=0, self_id=1, post_type="message", sub_type="normal",
                user_id=2, message_type="group", message_id=3, message=Message("命令"),
                original_message=Message("命令"), raw_message="命令", font=0,
                sender={"user_id":2,"card":"2","nickname":"真实昵称","role":"member"},
                to_me=False, group_id=10001)
            await handle_event(bot, event)
            assert handled == [True]
            assert h._member_nickname_cache[("1",10001,2)] == "真实昵称"

            silent_bot = SimpleNamespace(self_id="1", get_group_list=AsyncMock(return_value=[{"group_id":10001},{"group_id":10002}]),
                get_group_member_info=AsyncMock(side_effect=RuntimeError("member already left")),
                get_stranger_info=AsyncMock(return_value={"nickname":""}), send_group_msg=AsyncMock())
            async def members(group_id):
                if group_id == 10002:
                    raise RuntimeError("one group unavailable")
                # A stale roster must not overwrite the just-received message.
                return [{"user_id":2,"nickname":"旧昵称"},{"user_id":3,"card":"群名片","nickname":"未发言成员"}]
            silent_bot.get_group_member_list = AsyncMock(side_effect=members)
            await h._prime_member_nicknames(silent_bot)
            assert h._member_nickname_cache[("1",10001,2)] == "真实昵称"
            leave = GroupDecreaseNoticeEvent(time=0,self_id=1,post_type="notice",notice_type="group_decrease",
                sub_type="leave",user_id=3,group_id=10001,operator_id=3)
            await h.handle_leave_notice(silent_bot, leave)
            assert silent_bot.send_group_msg.await_args.kwargs["message"] == "群名片（3）离开了本群"
            assert ("1",10001,3) not in h._member_nickname_cache
            silent_bot.get_stranger_info.assert_not_awaited()
            assert await h._notice_nickname(silent_bot,10002,3) == "3"
            other_bot = SimpleNamespace(self_id="9",get_group_member_info=silent_bot.get_group_member_info,
                                        get_stranger_info=silent_bot.get_stranger_info)
            assert await h._notice_nickname(other_bot,10001,2) == "2"

            valid_bot = SimpleNamespace(self_id="1",get_group_member_info=AsyncMock(return_value={"card":"4","nickname":"资料昵称"}),
                                        get_stranger_info=AsyncMock())
            assert await h._notice_nickname(valid_bot,10001,4) == "资料昵称"
            valid_bot.get_stranger_info.assert_not_awaited()
            h.config.group_manager_join_notice_enabled = False
            join = GroupIncreaseNoticeEvent(time=0,self_id=1,post_type="notice",notice_type="group_increase",
                sub_type="approve",user_id=4,group_id=10001,operator_id=4)
            await h.handle_join_notice(valid_bot,join)
            assert h._member_nickname_cache[("1",10001,4)] == "资料昵称"

            failed_bot = SimpleNamespace(self_id="1",get_group_list=AsyncMock(side_effect=RuntimeError("offline")))
            await h._prime_member_nicknames(failed_bot)
        asyncio.run(scenario())
        """
    )
