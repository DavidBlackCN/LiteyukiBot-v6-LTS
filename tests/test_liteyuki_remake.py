from __future__ import annotations

import asyncio
from io import BytesIO
from types import SimpleNamespace

import nonebot
import pytest
from PIL import Image


def _plugin():
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init(command_start={"/"})
    plugin = nonebot.get_plugin("liteyuki_remake")
    return plugin or nonebot.load_plugin("src.nonebot_plugins.liteyuki_remake")


def test_plugin_loads_and_parses_random_command() -> None:
    assert _plugin() is not None
    from src.nonebot_plugins.liteyuki_remake import matcher_remake

    prefix = next((item for item in nonebot.get_driver().config.command_start if item), "")
    result = matcher_remake.command().parse(f"{prefix}remake --random")
    assert result.matched
    assert result.query("random.value") is True
    shortcut = matcher_remake.command().parse(f"{prefix}随机人生")
    assert shortcut.matched
    assert shortcut.query("random.value") is True


def test_bundled_conditions_are_safe_and_full_image_can_be_generated() -> None:
    _plugin()
    from src.nonebot_plugins.liteyuki_remake.drawer import draw_life, save_jpg
    from src.nonebot_plugins.liteyuki_remake.life import Life
    from src.nonebot_plugins.liteyuki_remake.utils import parse_condition

    life = Life()
    life.load()
    talents = life.rand_talents(10)[:3]
    life.set_talents(talents)
    life.apply_property({"CHR": 5, "INT": 5, "STR": 5, "MNY": 5})
    initial = life.get_property()
    results = list(life.run())
    output = save_jpg(draw_life(talents, initial, results, life.gen_summary()))

    assert output.tell() == 0
    with Image.open(output) as image:
        assert image.format == "JPEG"
        assert image.width > 0 and image.height > 0
    with pytest.raises(ValueError, match="不支持"):
        parse_condition('__import__("os").system("echo unsafe")')(SimpleNamespace())


def test_interactive_flow_generates_and_sends_image(monkeypatch: pytest.MonkeyPatch) -> None:
    _plugin()
    import src.nonebot_plugins.liteyuki_remake as remake

    responses = iter(("随机", "随机"))

    class PendingResponse:
        async def wait(self, timeout: int) -> str:
            return next(responses)

    def fake_waiter(**kwargs):
        def decorate(func):
            return PendingResponse()

        return decorate

    class OutgoingMessage:
        def __init__(self, raw: BytesIO):
            self.raw = raw

    class FakeUniMessage:
        @staticmethod
        def image(*, raw: BytesIO) -> OutgoingMessage:
            return OutgoingMessage(raw)

        @staticmethod
        def file(*, raw: BytesIO) -> OutgoingMessage:
            return OutgoingMessage(raw)

    class FakeMatcher:
        def __init__(self):
            self.messages: list[object] = []

        async def send(self, message: object) -> None:
            self.messages.append(message)

        async def finish(self, message: object = "") -> None:
            raise AssertionError(f"unexpected finish: {message}")

    async def fake_image(*args: object) -> BytesIO:
        return BytesIO(b"rendered-life")

    monkeypatch.setattr(remake, "waiter", fake_waiter)
    monkeypatch.setattr(remake, "UniMessage", FakeUniMessage)
    monkeypatch.setattr(remake, "get_life_img", fake_image)
    matcher = FakeMatcher()
    asyncio.run(remake._(matcher, SimpleNamespace(result=False)))

    assert any("请发送编号选择3个天赋" in str(message) for message in matcher.messages)
    assert any("请发送4个数字分配" in str(message) for message in matcher.messages)
    assert "你的人生正在重开..." in matcher.messages
    assert isinstance(matcher.messages[-1], OutgoingMessage)
    assert matcher.messages[-1].raw.getvalue() == b"rendered-life"
