from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

from PIL import Image

from test_liteyuki_twitter_parser import modules


def test_renderer_total_budget_verified_images_and_text_retention(monkeypatch):
    _, Config, Post, _ = modules()
    from src.nonebot_plugins.liteyuki_twitter import renderer
    from src.nonebot_plugins.liteyuki_twitter.models import Media
    from src.utils.base import resource
    from src.utils.message import html_tool
    buffer = BytesIO()
    Image.new("RGB", (10, 30), "blue").save(buffer, format="PNG")
    valid = buffer.getvalue() + b"\0" * (10 * 1024 * 1024 - len(buffer.getvalue()))
    calls, captured = [], {}
    class Client:
        async def download_image(self, url, **kwargs): calls.append(url); return valid, "image/png"
    async def screenshot(path, variables, selector, **kwargs):
        captured.update(variables["data"])
        assert selector == ".twitter-page"
        assert kwargs["wait_for"] == "window.twitterCardReady === true"
        return b"card"
    monkeypatch.setattr(resource, "get_path", lambda _: "fixture.html")
    monkeypatch.setattr(html_tool, "template2image_element", screenshot)
    post = Post("100", "example", text="正文" * 400, media=[Media(str(i)) for i in range(4)],
                quote=Post("50", "other", text="引用", media=[Media("quote")]))
    assert asyncio.run(renderer.render_card(post, Client(), Config())) == b"card"
    assert calls == ["0", "1", "2"]
    assert [bool(item["src"]) for item in captured["media"]] == [True, True, True, False]
    assert all(item["portrait"] for item in captured["media"][:3])
    assert not captured["quote"]["media"][0]["src"]
    assert "完整内容" in captured["body"] and len(post.text) == 800
    assert "引用" in renderer.text_message(post)


def test_invalid_image_and_translation_failure_keep_original(monkeypatch):
    _, Config, Post, _ = modules()
    from src.nonebot_plugins.liteyuki_twitter import renderer
    from src.nonebot_plugins.liteyuki_twitter.models import Media
    from src.utils.base import resource
    from src.utils.message import html_tool
    captured = {}
    class Client:
        async def download_image(self, *args, **kwargs): return b"invalid", "image/png"
    async def screenshot(path, variables, *args, **kwargs): captured.update(variables["data"]); return b"card"
    monkeypatch.setattr(resource, "get_path", lambda _: "fixture.html")
    monkeypatch.setattr(html_tool, "template2image_element", screenshot)
    post = Post("100", "example", text="original", translation_note="翻译失败", media=[Media("broken")])
    asyncio.run(renderer.render_card(post, Client(), Config()))
    assert captured["body"] == "original" and captured["translation_note"] == "翻译失败"
    assert captured["media"][0]["src"] == ""


def test_resource_pack_paths_and_safe_template():
    root = Path(__file__).resolve().parents[1] / "src/resources"
    pack = root / "liteyuki_twitter"
    assert (pack / "metadata.yml").exists()
    html = (pack / "templates/twitter_card.html").read_text(encoding="utf-8")
    for shared in ("css/card.css", "css/fonts.css", "js/card.js"):
        assert (root / "vanilla_resource/templates" / shared).exists()
        assert "./" + shared in html
        assert not (pack / "templates" / shared).exists()
    script = (pack / "templates/js/twitter_card.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script and "textContent" in script
    assert "Promise.allSettled" in script and "twitterCardReady" in script
