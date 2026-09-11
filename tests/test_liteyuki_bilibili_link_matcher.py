import asyncio


def _ensure_nonebot_initialized() -> None:
    import nonebot

    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()


def test_link_matcher_sends_one_card_for_one_resolved_link(monkeypatch) -> None:
    _ensure_nonebot_initialized()
    import src.nonebot_plugins.liteyuki_bilibili as plugin
    from src.nonebot_plugins.liteyuki_bilibili import link_matcher
    from src.nonebot_plugins.liteyuki_bilibili.config import BilibiliConfig
    from src.nonebot_plugins.liteyuki_bilibili.models import BilibiliEvent

    sent: list[object] = []

    class Event:
        def get_plaintext(self) -> str:
            return "看看 BV1xx411c7mD"

    class Matcher:
        async def send(self, message) -> None:
            sent.append(message)

    class Parser:
        def __init__(self, client) -> None:
            assert client is client_marker

        async def parse(self, link) -> BilibiliEvent:
            assert (link.kind, link.identifier) == ("video", "BV1xx411c7mD")
            return BilibiliEvent(kind="video", uid="42", event_id="BV1xx411c7mD", title="视频")

    class ImageMessage:
        async def send(self) -> None:
            sent.append("card")

    class UniMessage:
        @staticmethod
        def image(*, raw: bytes) -> ImageMessage:
            assert raw == b"card"
            return ImageMessage()

    class Client:
        async def start(self) -> None:
            pass

    client_marker = Client()
    monkeypatch.setattr(plugin, "config", BilibiliConfig())
    monkeypatch.setattr(link_matcher, "get_client", lambda: client_marker)
    monkeypatch.setattr(link_matcher, "resolve_links", _resolved_video)
    monkeypatch.setattr(link_matcher, "BilibiliLinkParser", Parser)
    monkeypatch.setattr(link_matcher, "UniMessage", UniMessage)
    monkeypatch.setattr(
        "src.nonebot_plugins.liteyuki_bilibili.renderer.render_event_card",
        _render_card,
    )

    asyncio.run(link_matcher.handle_bilibili_link(Event(), Matcher()))
    assert sent == ["card"]


def test_link_matcher_falls_back_to_text_when_rendering_fails(monkeypatch) -> None:
    _ensure_nonebot_initialized()
    import src.nonebot_plugins.liteyuki_bilibili as plugin
    from src.nonebot_plugins.liteyuki_bilibili import link_matcher
    from src.nonebot_plugins.liteyuki_bilibili.config import BilibiliConfig
    from src.nonebot_plugins.liteyuki_bilibili.models import BilibiliEvent

    sent: list[str] = []

    class Event:
        def get_plaintext(self) -> str:
            return "https://www.bilibili.com/video/BV1xx411c7mD"

    class Matcher:
        async def send(self, message: str) -> None:
            sent.append(message)

    class Parser:
        def __init__(self, client) -> None:
            pass

        async def parse(self, link) -> BilibiliEvent:
            return BilibiliEvent(kind="video", uid="42", event_id="BV1", title="视频")

    monkeypatch.setattr(plugin, "config", BilibiliConfig())
    class Client:
        async def start(self) -> None:
            pass

    monkeypatch.setattr(link_matcher, "get_client", lambda: Client())
    monkeypatch.setattr(link_matcher, "resolve_links", _resolved_video)
    monkeypatch.setattr(link_matcher, "BilibiliLinkParser", Parser)
    monkeypatch.setattr(
        "src.nonebot_plugins.liteyuki_bilibili.renderer.render_event_card",
        _render_failure,
    )

    asyncio.run(link_matcher.handle_bilibili_link(Event(), Matcher()))
    assert sent == ["Bilibili 发布了新视频｜UP 42\n视频"]


async def _resolved_video(text: str, client):
    from src.nonebot_plugins.liteyuki_bilibili.parser import BilibiliLink

    return [BilibiliLink("video", "BV1xx411c7mD", "")]


async def _render_card(event, client, scale: float) -> bytes:
    return b"card"


async def _render_failure(event, client, scale: float) -> bytes:
    raise RuntimeError("render unavailable")
