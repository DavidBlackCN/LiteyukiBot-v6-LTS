import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import types

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/nonebot_plugins/liteyuki_group_manager"
PACKAGE = "_group_manager_bot_admin_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(SOURCE)]
sys.modules[PACKAGE] = package
spec = importlib.util.spec_from_file_location(f"{PACKAGE}.admin_store", SOURCE / "admin_store.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Store = module.BotAdminOverrideStore


def test_override_storage_roundtrip_and_corruption(tmp_path, monkeypatch):
    path = tmp_path / "admins.json"
    store = Store(path)
    store.load()
    assert json.loads(path.read_text(encoding="utf-8")) == {"groups": {}}
    store.set_override(100, 1, True)
    store.set_override(100, 2, False)
    store.set_override(200, 1, False)
    assert store.get_override(100, 1) is True
    assert store.get_override(100, 2) is False
    assert store.get_override(200, 1) is False
    assert Store(path).path == path
    reloaded = Store(path)
    reloaded.load()
    assert reloaded.group_overrides(100) == {"grant": ["1"], "deny": ["2"]}
    reloaded.reset_override(100, 1)
    assert reloaded.get_override(100, 1) is None
    original = path.read_bytes()
    def fail_replace(*args):
        raise OSError("mock disk failure")
    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError):
        reloaded.set_override(100, 9, True)
    assert path.read_bytes() == original
    assert reloaded.get_override(100, 9) is None
    assert not list(path.parent.glob("admins-*.tmp"))
    monkeypatch.undo()
    path.write_text("{broken", encoding="utf-8")
    damaged = Store(path)
    damaged.load()
    assert damaged.storage_error
    assert damaged.get_override(100, 1) is None
    with pytest.raises(ValueError):
        damaged.set_override(100, 1, True)
    assert path.read_text(encoding="utf-8") == "{broken"


def run_python(source, tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8",
               BOT_ADMIN_TEST_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, "-c", textwrap.dedent(source)],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bot_admin_roles_permission_and_access_integration(tmp_path):
    run_python('''
        import asyncio
        import os
        from types import SimpleNamespace

        import nonebot
        from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, Message

        nonebot.init(
            superusers={"99"},
            group_manager_admin_data_path=os.environ["BOT_ADMIN_TEST_DIR"],
            access_control_data_path=os.environ["BOT_ADMIN_TEST_DIR"],
        )
        driver = nonebot.get_driver()
        driver.register_adapter(Adapter)
        bot = Bot(driver._adapters[Adapter.get_name()], "1")

        from src.nonebot_plugins.liteyuki_group_manager.core import has_management_permission
        from src.nonebot_plugins.liteyuki_group_manager.handlers import bot_admin
        from src.nonebot_plugins.liteyuki_group_manager.permission import (
            ADMIN, BOT_ROLE_ADMIN, BOT_ROLE_SUPERUSER, BOT_ROLE_USER,
            bot_admin_overrides, get_bot_role,
        )
        from src.nonebot_plugins.liteyuki_access_control import commands

        def event(user_id, role="member", group_id=100):
            return GroupMessageEvent(
                time=0, self_id=1, post_type="message", sub_type="normal",
                user_id=user_id, message_type="group", message_id=3, message=Message(),
                original_message=Message(), raw_message="", font=0,
                sender={"role": role}, to_me=False, group_id=group_id,
            )

        async def main():
            assert await get_bot_role(bot, event(99)) == BOT_ROLE_SUPERUSER
            assert await get_bot_role(bot, event(1, "owner")) == BOT_ROLE_ADMIN
            assert await get_bot_role(bot, event(2, "admin")) == BOT_ROLE_ADMIN
            assert await get_bot_role(bot, event(3, "member")) == BOT_ROLE_USER

            from src.nonebot_plugins.liteyuki_group_manager.config import group_manager_config
            group_manager_config.group_manager_admin_auto_roles = ["owner"]
            assert await get_bot_role(bot, event(2, "admin")) == BOT_ROLE_USER
            assert await get_bot_role(bot, event(1, "owner")) == BOT_ROLE_ADMIN
            group_manager_config.group_manager_admin_auto_roles = []
            assert await get_bot_role(bot, event(1, "owner")) == BOT_ROLE_USER

            bot_admin_overrides.set_override(100, 3, True)
            assert await get_bot_role(bot, event(3)) == BOT_ROLE_ADMIN
            bot_admin_overrides.set_override(100, 1, False)
            assert await get_bot_role(bot, event(1, "owner")) == BOT_ROLE_USER
            assert await get_bot_role(bot, event(99, "owner")) == BOT_ROLE_SUPERUSER
            bot_admin_overrides.reset_override(100, 1)
            group_manager_config.group_manager_admin_auto_roles = ["owner", "admin"]
            assert await get_bot_role(bot, event(1, "owner")) == BOT_ROLE_ADMIN
            assert await get_bot_role(bot, event(1, "owner", 200)) == BOT_ROLE_ADMIN
            assert await get_bot_role(bot, event(3, "member", 200)) == BOT_ROLE_USER

            assert await ADMIN(bot, event(3))
            assert not await bot_admin.permission(bot, event(3))
            assert await bot_admin.permission(bot, event(99))
            assert await ADMIN(bot, event(99))
            assert not await ADMIN(bot, event(4))
            # A Bot ADMIN remains a QQ member and cannot use QQ moderation commands.
            assert not has_management_permission("member", False)

            assert await commands.access.permission(bot, event(3))
            commands.execute_command("disable plugin foo", 100, bot_admin=True)
            assert commands.controller.rules["group_plugins"]["100"]["foo"] is False
            commands.execute_command("enable plugin foo", 100, bot_admin=True)
            assert commands.controller.rules["group_plugins"]["100"]["foo"] is True
            for text in ("status", "blacklist-user 4", "limit set foo 1 60",
                         "disable plugin foo"):
                try:
                    commands.execute_command(text, None, bot_admin=True)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Bot ADMIN unexpectedly ran: {text}")
        asyncio.run(main())
    ''', tmp_path)
