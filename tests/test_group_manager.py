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
