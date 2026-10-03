"""Built-in game commands work without mentioning the bot."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("require_tome", [False, True])
def test_game_command_rules_and_handle_start(require_tome):
    source = '''
        import asyncio
        from types import SimpleNamespace
        import nonebot
        from nonebot.adapters.onebot.v11 import Adapter as V11, Bot, GroupMessageEvent, Message
        from nonebot.adapters.onebot.v12 import Adapter as V12

        nonebot.init(command_start={"", "/"}, handle_require_tome=REQUIRE_TOME)
        driver = nonebot.get_driver()
        driver.register_adapter(V11)
        driver.register_adapter(V12)
        nonebot.require("nonebot_plugin_alconna")
        for name in ("liteyuki_remake", "trimo_plugin_handle", "trimo_plugin_dockdragon"):
            assert nonebot.load_plugin("src.nonebot_plugins." + name) is not None

        from src.nonebot_plugins import liteyuki_remake as remake
        from src.nonebot_plugins import trimo_plugin_handle as handle
        from src.nonebot_plugins import trimo_plugin_dockdragon as dragon

        def checks(matcher):
            pending = list(matcher.rule.checkers)
            calls = set()
            while pending:
                call = pending.pop().call
                calls.add(getattr(call, "__name__", type(call).__name__))
                for name in ("before_rules", "after_rules"):
                    rule = getattr(call, name, None)
                    if rule is not None:
                        pending.extend(rule.checkers)
            return calls

        from nonebot.rule import to_me
        tome_checks = {type(checker.call).__name__ for checker in to_me().checkers}
        assert not checks(remake.matcher_remake) & tome_checks
        assert not checks(dragon.handle) & tome_checks
        assert bool(checks(handle.handle_matcher) & tome_checks) == REQUIRE_TOME
        assert "game_not_running" in checks(handle.handle_matcher)
        assert "game_not_running" in checks(dragon.handle)

        for matcher, commands in (
            (remake.matcher_remake, ("remake --random", "人生重开", "随机人生")),
            (handle.handle_matcher, ("handle", "猜成语", "猜成语 -s -d")),
            (dragon.handle, ("dockdragon", "接龙")),
        ):
            for command in commands:
                assert matcher.command().parse(command).matched, command
                assert matcher.command().parse("/" + command).matched, command
            assert not matcher.command().parse("今天随便聊聊").matched

        bot = Bot(driver._adapters[V11.get_name()], "1")
        event = GroupMessageEvent(
            time=0, self_id=1, post_type="message", sub_type="normal", user_id=2,
            message_type="group", message_id=3, message=Message("人生重开"),
            original_message=Message("人生重开"), raw_message="人生重开", font=0,
            sender={"role": "member"}, to_me=False, group_id=100,
        )
        assert asyncio.run(remake.matcher_remake.rule(bot, event, {}))

        # Exercise the handler too: its former extra mention/header guard must
        # not silently discard a parsed command with no prefix or mention.
        sent = []
        class FakeHandle:
            times = 10
            def __init__(self, *args, **kwargs): pass
            def draw(self): return b"card"
        class Outgoing:
            def __add__(self, other): return self
            async def send(self): sent.append("started")
        handle.Handle = FakeHandle
        handle.random_idiom = lambda *_: ("顺其自然", "释义")
        handle.set_timeout = lambda *_: None
        handle.Text = lambda *_: Outgoing()
        handle.Image = lambda **_: Outgoing()
        result = handle.handle_matcher.command().parse("handle")
        async def run():
            await handle.handle_matcher.handlers[0].call(result, SimpleNamespace(), "scene")
        asyncio.run(run())
        assert sent == ["started"]
        assert not handle.game_not_running("scene")
        assert handle.game_is_running("scene")
    '''.replace("REQUIRE_TOME", repr(require_tome))
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)], cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8"),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_upstream_idiom_entries_are_consistent():
    import json

    data = ROOT / "src/nonebot_plugins/trimo_plugin_handle/resources/data"
    common = json.loads((data / "common_idioms.json").read_text(encoding="utf-8"))
    legal = json.loads((data / "idioms.json").read_text(encoding="utf-8"))
    answers = json.loads((data / "answers.json").read_text(encoding="utf-8"))
    expected = {
        "擅离职守": ["shan4", "li2", "zhi2", "shou3"],
        "善解人意": ["shan4", "jie3", "ren2", "yi4"],
        "不容小觑": ["bu4", "rong2", "xiao3", "qu4"],
        "浑然不觉": ["hun2", "ran2", "bu4", "jue2"],
        "顺其自然": ["shun4", "qi2", "zi4", "ran2"],
    }
    for word, pinyin in expected.items():
        assert common.count(word) == legal.count(word) == 1
        assert answers[word]["pinyin"] == pinyin
        assert answers[word]["explanation"]
