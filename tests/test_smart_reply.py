from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_python(source: str, **extra_env: str) -> None:
    env = os.environ.copy()
    env.update(extra_env)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    assert result.returncode == 0, (
        f"subprocess failed with code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_smart_reply_loads_from_builtin_plugin_directory() -> None:
    _run_python(
        """
        import nonebot
        import liteyuki.utils
        from nonebot.adapters.onebot.v11 import Adapter as V11Adapter
        from nonebot.adapters.onebot.v12 import Adapter as V12Adapter

        liteyuki.utils.IS_MAIN_PROCESS = False
        from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

        nonebot.init()
        driver = nonebot.get_driver()
        driver.register_adapter(V11Adapter)
        driver.register_adapter(V12Adapter)
        starter._load_htmlrender_plugin()
        starter._load_alconna_plugin()
        nonebot.plugin.load_plugins("src/nonebot_plugins")

        plugin = nonebot.get_plugin("liteyuki_smart_reply")
        assert plugin is not None
        assert plugin.metadata.extra["toggleable"] is True
        assert plugin.metadata.extra["default_enable"] is True

        from nonebot.consts import CMD_KEY, PREFIX_KEY
        from src.nonebot_plugins.liteyuki_smart_reply.matchers import is_registered_command

        weather = nonebot.get_plugin("liteyuki_weather")
        assert weather is not None
        assert is_registered_command("/天气", {}, [weather])
        assert is_registered_command("/weather 深圳", {}, [weather])
        assert is_registered_command(
            "anything", {PREFIX_KEY: {CMD_KEY: ("registered",)}}, []
        )
        assert not is_registered_command("/不存在的命令", {}, [weather])
        assert not is_registered_command("今天天气真好", {}, [weather])
        """
    )


def test_group_probability_persistence_validation_and_pacman_toggle(
    tmp_path: Path,
) -> None:
    _run_python(
        """
        import asyncio
        import math
        import os
        from datetime import datetime

        import nonebot
        from nonebot.adapters.onebot.v11 import Adapter, GroupMessageEvent
        from nonebot.adapters.onebot.v12 import GroupMessageEvent as V12GroupMessageEvent
        from nonebot.exception import IgnoredException

        nonebot.init()
        nonebot.get_driver().register_adapter(Adapter)
        plugin = nonebot.load_plugin(
            "src.nonebot_plugins.liteyuki_smart_reply"
        )
        assert plugin is not None

        from src.nonebot_plugins.liteyuki_smart_reply import matchers
        from src.nonebot_plugins.liteyuki_pacman import common, npm
        from src.utils import event as event_utils
        from src.utils.base.data import Database
        from src.utils.base.data_manager import Group

        database = Database(os.path.join(os.environ["SMART_REPLY_TMP"], "groups.ldb"))
        database.auto_migrate(Group())
        matchers.group_db = database
        common.group_db = database

        matchers.save_group_probability(10001, 0.25)
        matchers.save_group_probability("10002", 0.8)
        assert matchers.get_group_probability("10001") == 0.25
        assert matchers.get_group_probability(10001) == 0.25
        assert set(matchers.group_reply_probability) == {"10001", "10002"}

        matchers.group_reply_probability.clear()
        matchers.load_group_probabilities()
        assert matchers.get_group_probability(10001) == 0.25
        assert matchers.get_group_probability("10002") == 0.8
        assert matchers.get_group_probability(99999) == 0.05

        for valid in (0, 0.05, 1):
            assert matchers.is_valid_probability(valid)
        for invalid in (-0.1, 1.1, math.nan, math.inf):
            assert not matchers.is_valid_probability(invalid)
            try:
                matchers.save_group_probability("invalid", invalid)
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid probability accepted: {invalid}")

        event = GroupMessageEvent(
            time=0,
            self_id=1,
            post_type="message",
            sub_type="normal",
            user_id=2,
            message_type="group",
            message_id=3,
            message=[],
            original_message=[],
            raw_message="",
            font=0,
            sender={},
            to_me=False,
            group_id=10001,
        )
        assert event_utils.get_group_id(event) == 10001
        assert matchers.get_group_probability(event_utils.get_group_id(event)) == 0.25

        v12_event = V12GroupMessageEvent(
            id="event-1",
            time=datetime.now(),
            type="message",
            detail_type="group",
            sub_type="normal",
            self={"platform": "qq", "user_id": "1"},
            message_id="3",
            message=[],
            original_message=[],
            alt_message="",
            user_id="2",
            group_id="10002",
        )
        assert event_utils.get_message_type(v12_event) == "group"
        assert event_utils.get_group_id(v12_event) == "10002"
        assert matchers.get_group_probability(event_utils.get_group_id(v12_event)) == 0.8

        common.set_plugin_session_enable(event, "liteyuki_smart_reply", False)
        assert not common.get_plugin_session_enable(event, "liteyuki_smart_reply")

        npm.get_plugin_global_enable = lambda _: True
        npm.get_plugin_session_enable = common.get_plugin_session_enable
        matcher = next(iter(plugin.matcher))

        async def verify_toggle():
            try:
                await npm.pre_handle(event, matcher)
            except IgnoredException:
                pass
            else:
                raise AssertionError("disabled Smart Reply matcher was not blocked")

            common.set_plugin_session_enable(event, "liteyuki_smart_reply", True)
            assert common.get_plugin_session_enable(event, "liteyuki_smart_reply")
            await npm.pre_handle(event, matcher)

        asyncio.run(verify_toggle())
        """,
        SMART_REPLY_TMP=str(tmp_path),
    )
