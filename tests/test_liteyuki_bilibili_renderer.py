import asyncio
from datetime import UTC, datetime
from pathlib import Path

import nonebot

from src.nonebot_plugins.liteyuki_bilibili.models import BilibiliEvent, BilibiliSubscription


def _init() -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()


def test_templates_use_shared_liteyuki_assets_and_local_data_contract() -> None:
    for name in ("bilibili_video.html", "bilibili_dynamic.html", "bilibili_live.html"):
        template = Path("src/resources/liteyuki_bilibili/templates", name).read_text(encoding="utf-8")
        assert "./css/card.css" in template
        assert "./css/fonts.css" in template
        assert "./js/card.js" in template
        assert "{{ data | tojson }}" in template
        assert 'class="covers"' in template
        assert "http://" not in template and "https://" not in template
    assert not list(Path("src/resources/liteyuki_bilibili").rglob("*.woff*"))


def test_event_view_handles_long_text_and_metrics() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_bilibili.renderer import event_view

    view = event_view(BilibiliEvent(kind="video", uid="42", event_id="BV1", body="测" * 2000, metrics={"view": 123, "like": 0}))
    assert len(view["body"]) == 1600
    assert view["metrics"] == [{"label": "播放", "value": "123"}, {"label": "点赞", "value": "0"}]


def test_renderer_embeds_valid_images_and_ignores_failed_ones(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_bilibili.client import DownloadedImage
    from src.nonebot_plugins.liteyuki_bilibili import renderer

    class Client:
        async def download_image(self, url: str):
            if url == "https://i0.hdslb.com/broken.jpg":
                raise RuntimeError("image unavailable")
            return DownloadedImage(b"image", "image/png")

    captured = {}

    async def fake_render(template, variables, selector, **kwargs):
        captured.update(template=template, variables=variables, selector=selector, kwargs=kwargs)
        return b"png"

    monkeypatch.setattr(renderer, "get_path", lambda *_args, **_kwargs: "template.html")
    monkeypatch.setattr(renderer, "template2image_element", fake_render)
    event = BilibiliEvent(
        kind="dynamic",
        uid="42",
        event_id="1",
        avatar_url="https://i0.hdslb.com/broken.jpg",
        cover_urls=["https://i0.hdslb.com/cover.jpg"],
    )
    assert asyncio.run(renderer.render_event_card(event, Client(), 1.5)) == b"png"
    data = captured["variables"]["data"]
    assert data["avatar"] == ""
    assert data["covers"] == ["data:image/png;base64,aW1hZ2U="]
    assert captured["selector"] == "body"
    assert captured["kwargs"]["scale_factor"] == 1.5


def test_delivery_falls_back_to_text_when_card_rendering_fails(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_bilibili import delivery, renderer

    sent = []

    class Bot:
        async def send_group_msg(self, **kwargs) -> None:
            sent.append(kwargs["message"])

    async def fail_render(*_args, **_kwargs) -> bytes:
        raise RuntimeError("playwright unavailable")

    monkeypatch.setattr(delivery, "choose_push_bot", lambda: Bot())
    monkeypatch.setattr(renderer, "render_event_card", fail_render)
    subscription = BilibiliSubscription(
        target_type="group",
        target_id="100",
        uid="42",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    event = BilibiliEvent(kind="video", uid="42", event_id="BV1", title="测试视频")
    assert asyncio.run(delivery.deliver_event(subscription, event, object()))
    assert "测试视频" in sent[0]
