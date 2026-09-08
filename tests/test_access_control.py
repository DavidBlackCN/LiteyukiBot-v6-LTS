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
SOURCE = ROOT / "src/nonebot_plugins/liteyuki_access_control"
# Load pure rule modules without executing the actual plugin entry point.
PACKAGE = "_access_control_unit_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(SOURCE)]
sys.modules[PACKAGE] = package
for name in ("config", "engine"):
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{name}", SOURCE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
Config = sys.modules[f"{PACKAGE}.config"].AccessControlConfig
Controller = sys.modules[f"{PACKAGE}.engine"].AccessController


@pytest.fixture
def control(tmp_path):
    instance = Controller(Config(access_control_data_path=str(tmp_path)))
    instance.load()
    return instance


def test_default_allow_and_smart_reply(control):
    assert control.allowed("foo", "u", "g")
    assert control.allowed("liteyuki_smart_reply", "u", "g")


@pytest.mark.parametrize("scope", ["user", "group"])
def test_blacklist_precedes_whitelist_and_enable(control, scope):
    subject = "u" if scope == "user" else "g"
    control.set_list(subject, scope=scope)
    control.set_list(subject, scope=scope, whitelist=True)
    control.set_plugin("foo", subject, scope=scope, enabled=True)
    assert not control.allowed("foo", "u", "g")
    control.set_list(subject, scope=scope, remove=True)
    assert control.allowed("foo", "u", "g")


@pytest.mark.parametrize("scope", ["user", "group"])
def test_plugin_disable_and_enable(control, scope):
    subject = "u" if scope == "user" else "g"
    control.set_plugin("foo", subject, scope=scope, enabled=False)
    assert not control.allowed("foo", "u", "g")
    assert control.allowed("other", "u", "g")
    control.set_plugin("foo", subject, scope=scope, enabled=True)
    assert control.allowed("foo", "u", "g")


def test_explicit_denial_wins_over_other_scope_allow(control):
    control.set_plugin("foo", "g", enabled=False)
    control.set_plugin("foo", "u", scope="user", enabled=True)
    assert not control.allowed("foo", "u", "g")


def test_default_deny_whitelist(control):
    control.config.access_control_default_allow = False
    assert not control.allowed("foo", "u", "g")
    control.set_list("u", whitelist=True)
    assert control.allowed("foo", "u", "g")
    control.set_plugin("foo", "g", enabled=False)
    assert not control.allowed("foo", "u", "g")


def test_superuser_and_protection(control):
    control.set_list("u")
    assert control.allowed("foo", "u", superuser=True)
    control.set_limit("foo", 1, 60)
    for _ in range(3):
        assert control.rate_allowed("foo", "u", superuser=True)
    control.config.access_control_superuser_bypass = False
    assert not control.allowed("foo", "u", superuser=True)
    for name in ("liteyuki_access_control", "liteyuki_group_manager"):
        assert control.allowed(name, "u")
        with pytest.raises(ValueError):
            control.set_plugin(name, "g", enabled=False)
        with pytest.raises(ValueError):
            control.set_limit(name, 1, 60)


def test_sliding_window_and_cleanup(control):
    now = [0.0]
    control.clock = lambda: now[0]
    control.set_limit("foo", 2, 60)
    assert control.rate_allowed("foo", "u", "g1")
    assert control.rate_allowed("foo", "u", "g2")
    assert not control.rate_allowed("foo", "u", "g1")
    now[0] = 60
    assert control.rate_allowed("foo", "u")
    now[0] = 120
    control.cleanup()
    assert not control.buckets


def test_disabled_allows_everything(control):
    control.set_list("u")
    control.set_limit("foo", 1, 60)
    control.config.access_control_enabled = False
    for _ in range(3):
        assert control.allowed("foo", "u")
        assert control.rate_allowed("foo", "u")


def test_roundtrip_and_atomic_failure(control, monkeypatch):
    control.set_plugin("foo", "g", enabled=False)
    control.set_list("u", whitelist=True)
    control.set_limit("foo", 2, 60)
    reloaded = Controller(control.config)
    reloaded.load()
    assert reloaded.rules == control.rules
    original = control.path.read_bytes()
    def fail(*args):
        raise OSError("mock disk failure")
    monkeypatch.setattr(sys.modules[f"{PACKAGE}.engine"].os, "replace", fail)
    with pytest.raises(OSError):
        control.set_list("blocked")
    assert control.path.read_bytes() == original
    assert "blocked" not in control.rules["blacklist_user"]
    assert not list(control.path.parent.glob("rules-*.tmp"))


@pytest.mark.parametrize("content", ["not json", '{"version":1,"limits":{"foo":{"count":0,"window":60}}}', '[]'])
def test_corruption_preserved(tmp_path, content):
    (tmp_path / "rules.json").write_text(content, encoding="utf-8")
    control = Controller(Config(access_control_data_path=str(tmp_path)))
    control.load()
    assert control.storage_error
    assert control.allowed("foo", "u")
    assert control.path.read_text(encoding="utf-8") == content
    with pytest.raises(ValueError):
        control.set_list("u")


def run_python(source, tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8", ACCESS_TEST_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, "-c", textwrap.dedent(source)],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_nonebot_hook_and_commands(tmp_path):
    run_python('''
        import asyncio, os
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import nonebot
        from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, Message
        from nonebot.exception import IgnoredException
        nonebot.init(access_control_data_path=os.environ["ACCESS_TEST_DIR"], superusers={"onebot:99"})
        driver = nonebot.get_driver()
        driver.register_adapter(Adapter)
        plugin = nonebot.load_plugin("src.nonebot_plugins.liteyuki_access_control")
        assert plugin is not None
        from src.nonebot_plugins.liteyuki_access_control import hooks, api, commands
        bot = Bot(driver._adapters[Adapter.get_name()], "1")
        bot.send = AsyncMock()
        event = GroupMessageEvent(time=0, self_id=1, post_type="message", sub_type="normal",
            user_id=2, message_type="group", message_id=3, message=Message("x"),
            raw_message="x", font=0, sender={"role":"member"}, group_id=100)
        matcher = SimpleNamespace(plugin=SimpleNamespace(name="foo"))
        assert hooks.context_ids(matcher, event) == ("foo", "2", "100")
        assert hooks.context_ids(SimpleNamespace(), SimpleNamespace()) == (None, None, None)
        async def main():
            assert not await commands.access.permission(bot, event)
            assert await api.is_allowed("liteyuki_smart_reply", "2", "100")
            commands.execute_command("disable plugin foo", 100)
            try:
                await hooks.guard(bot, event, matcher)
            except IgnoredException:
                pass
            else:
                raise AssertionError("disabled matcher ran")
            assert bot.send.await_count == 1
            await hooks.clear_decisions(bot, event)
            commands.execute_command("enable plugin foo", 100)
            commands.execute_command("limit set foo 1 60")
            await hooks.guard(bot, event, matcher)
            await hooks.guard(bot, event, matcher)
            assert len(next(iter(api.controller.buckets.values()))) == 1
            await hooks.clear_decisions(bot, event)
            try:
                await hooks.guard(bot, event, matcher)
            except IgnoredException:
                pass
            else:
                raise AssertionError("rate limit ignored")
            await hooks.clear_decisions(bot, event)
            event.user_id = 99
            assert await commands.access.permission(bot, event)
            commands.execute_command("blacklist-user 99")
            await hooks.guard(bot, event, matcher)
            await hooks.clear_decisions(bot, event)
            assert not hooks._decisions
        asyncio.run(main())
    ''', tmp_path)


def test_disabled_plugin_has_no_hooks_or_storage(tmp_path):
    run_python('''
        import os
        from pathlib import Path
        import nonebot
        from nonebot.message import _run_preprocessors
        nonebot.init(access_control_enabled=False, access_control_data_path=os.environ["ACCESS_TEST_DIR"])
        before = set(_run_preprocessors)
        plugin = nonebot.load_plugin("src.nonebot_plugins.liteyuki_access_control")
        assert plugin is not None and not plugin.matcher
        assert before == _run_preprocessors
        assert not (Path(os.environ["ACCESS_TEST_DIR"]) / "rules.json").exists()
    ''', tmp_path)
