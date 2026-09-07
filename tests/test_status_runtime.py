from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_status_background_fallback_and_onebot_qq_avatar() -> None:
    source = """
import asyncio
import base64
import nonebot
import liteyuki.utils
from nonebot.adapters.onebot.v11 import Adapter

liteyuki.utils.IS_MAIN_PROCESS = False
from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)
starter._load_htmlrender_plugin()
starter._load_alconna_plugin()
assert nonebot.load_plugin("src.nonebot_plugins.trimo_status") is not None

from src.nonebot_plugins.trimo_status import api
from src.nonebot_plugins.trimo_status.config import TrimoStatusConfig

assert TrimoStatusConfig().status_background_mask == 0.35


class FakeResponse:
    headers = {"Content-Type": "image/png"}
    url = "https://cdn.example.test/final.png"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        return None

    async def read(self):
        return b"valid-image"


class FakeSession:
    def __init__(self, *, timeout):
        assert timeout.total == 4

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url):
        assert url == "https://example.test/background"
        return FakeResponse()


class OfflineSession:
    def __init__(self, **kwargs):
        raise api.aiohttp.ClientError("offline")


class FakeOneBot:
    self_id = "123456"

    async def get_login_info(self):
        return {"nickname": "Test Bot"}

    async def get_group_list(self):
        return [1, 2]

    async def get_friend_list(self):
        return [1]

    async def get_status(self):
        return {"stat": {"message_sent": 3, "message_received": 4}}

    async def get_version_info(self):
        return {"app_name": "SnowLuma", "protocol_name": 0}


async def main():
    debug_logs = []

    class FakeLogger:
        def debug(self, message):
            debug_logs.append(message)

    api.nonebot.logger = FakeLogger()
    api.status_config.status_background_enabled = True
    api.status_config.status_background_url = "https://example.test/background"
    api.status_config.status_background_timeout = 4
    api.status_config.status_background_mask = 0.68
    api.aiohttp.ClientSession = FakeSession

    background = await api.get_status_background()
    assert background == {
        "image": "data:image/png;base64," + base64.b64encode(b"valid-image").decode(),
        "mask": 0.68,
    }
    assert debug_logs == [
        "Status background loaded: url=https://cdn.example.test/final.png, "
        "content_type=image/png, size=11 bytes"
    ]

    api.aiohttp.ClientSession = OfflineSession
    assert await api.get_status_background() == background
    api.status_config.status_background_url = "https://example.test/other"
    assert await api.get_status_background() == {"image": None, "mask": 0.68}

    api.nonebot.get_bots = lambda: {"123456": FakeOneBot()}
    bots = await api.get_bots_data()
    assert bots["bots"][0]["app_name"] == "SnowLuma"
    assert bots["bots"][0]["icon"] == "https://q.qlogo.cn/g?b=qq&nk=123456&s=640"
    assert bots["bots"][0]["groups"] == 2
    assert bots["bots"][0]["friends"] == 1

    render_call = {}

    async def fake_background():
        return {"image": None, "mask": 0.35}

    async def fake_local_data(lang):
        return {"language": lang}

    async def fake_template2image_element(template, templates, selector, **kwargs):
        render_call.update(template=template, templates=templates, kwargs=kwargs)
        render_call["selector"] = selector
        return b"rendered"

    api.get_status_background = fake_background
    api.get_local_data = fake_local_data
    api.get_path = lambda *args, **kwargs: "status.html"
    api.template2image_element = fake_template2image_element
    rendered = await api.generate_status_card({}, {}, {}, lang="zh-CN")
    assert rendered == b"rendered"
    assert render_call["selector"] == ".status-page"
    assert render_call["kwargs"]["wait_for"] == "window.statusBackgroundReady === true"
    assert render_call["templates"]["data"]["background"]["image"] is None


asyncio.run(main())
"""
    env = os.environ.copy()
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
    assert result.returncode == 0, result.stdout + result.stderr
