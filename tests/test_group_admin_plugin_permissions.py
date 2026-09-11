import os
from pathlib import Path
import subprocess
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[1]


def run_python(source: str, tmp_path: Path) -> None:
    env = dict(
        os.environ,
        PYTHONPATH=str(ROOT),
        PYTHONIOENCODING="utf-8",
        PLUGIN_ADMIN_TEST_DIR=str(tmp_path),
    )
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_current_group_admin_matchers_and_superuser_boundaries(tmp_path: Path) -> None:
    run_python(
        '''
        import asyncio
        import os
        from pathlib import Path

        import nonebot
        import liteyuki.utils
        from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, Message

        liteyuki.utils.IS_MAIN_PROCESS = False
        from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

        nonebot.init(
            superusers={"99"},
            group_manager_admin_data_path=os.environ["PLUGIN_ADMIN_TEST_DIR"],
        )
        driver = nonebot.get_driver()
        driver.register_adapter(Adapter)
        starter._load_htmlrender_plugin()
        starter._load_alconna_plugin()
        for module in (
            "src.nonebot_plugins.liteyuki_setu",
            "src.nonebot_plugins.liteyuki_bilibili",
            "src.nonebot_plugins.liteyuki_smart_reply",
            "src.nonebot_plugins.liteyuki_pacman",
            "src.nonebot_plugins.liteyuki_eventpush",
        ):
            assert nonebot.load_plugin(module) is not None

        from src.nonebot_plugins.liteyuki_group_manager.permission import bot_admin_overrides
        from src.nonebot_plugins.liteyuki_setu.admin import setu_admin
        from src.nonebot_plugins.liteyuki_bilibili.commands import (
            login, login_status, logout, migrate, subscribe, subscription_list, unsubscribe,
        )
        from src.nonebot_plugins.liteyuki_eventpush import add_push
        from src.nonebot_plugins.liteyuki_pacman import npm

        bot = Bot(driver._adapters[Adapter.get_name()], "1")

        def event(user_id, role="member", group_id=100):
            return GroupMessageEvent(
                time=0, self_id=1, post_type="message", sub_type="normal",
                user_id=user_id, message_type="group", message_id=3, message=Message(),
                original_message=Message(), raw_message="", font=0,
                sender={"role": role}, to_me=False, group_id=group_id,
            )

        def matcher_for(command):
            for plugin in nonebot.get_loaded_plugins():
                for matcher in plugin.matcher:
                    if hasattr(matcher, "command") and str(matcher.command().command) == command:
                        return matcher
            raise AssertionError(f"matcher not found: {command}")

        async def main():
            granted = event(3)
            owner = event(4, "owner")
            member = event(5)
            superuser = event(99)
            bot_admin_overrides.set_override(100, 3, True)
            bot_admin_overrides.set_override(100, 4, False)

            current_group_matchers = (
                setu_admin, subscribe, unsubscribe, subscription_list,
                matcher_for("set-reply-probability"),
            )
            for matcher in current_group_matchers:
                assert await matcher.permission(bot, granted)
                assert await matcher.permission(bot, superuser)
                assert not await matcher.permission(bot, member)
                assert not await matcher.permission(bot, owner)

            # A Bot ADMIN cannot access any Bilibili credential command or lep.
            for matcher in (login, login_status, logout, migrate, add_push):
                assert not await matcher.permission(bot, granted)
                assert await matcher.permission(bot, superuser)

            # The command-level Pacman guards retain SUPERUSER-only global actions.
            assert not npm.can_manage_global({npm.enable_global: object()}, False)
            assert npm.can_manage_global({npm.enable_global: object()}, True)
            source = Path(npm.__file__).read_text(encoding="utf-8")
            assert "elif await is_admin(bot, event):" in source
            assert "if not perm_s:" in source
            assert "GROUP_ADMIN" not in source and "GROUP_OWNER" not in source

        asyncio.run(main())
        ''',
        tmp_path,
    )
