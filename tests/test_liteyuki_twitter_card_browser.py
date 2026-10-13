"""Offline checks of translation labels using an existing Chromium."""
import os
import shutil
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

from test_liteyuki_twitter_parser import modules


def test_card_translation_labels_match_provider_on_success_and_failure(tmp_path, monkeypatch):
    _, _, Post, _ = modules()
    from src.nonebot_plugins.liteyuki_twitter.renderer import view_model

    local = os.environ.get("LOCALAPPDATA")
    cache = Path(local) / "nonebot2/nonebot_plugin_htmlrender" if local else None
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH") and cache and cache.exists():
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(cache))
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("No existing Chromium; browser downloads are disabled")
        for pack in ("vanilla_resource", "liteyuki_twitter"):
            shutil.copytree(Path("src/resources") / pack / "templates", tmp_path, dirs_exist_ok=True)
        template = Environment(loader=FileSystemLoader(tmp_path), autoescape=True).get_template("twitter_card.html")
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1080, "height": 10})
            posts = [
                Post("100", "example", text="Original", translation="模型译文", translation_provider="model",
                     quote=Post("50", "other", text="Quote", translation="引用译文", translation_provider="model")),
                Post("101", "example", text="Long original " * 100, translation_note="翻译服务连接失败或超时",
                     translation_provider="model"),
                Post("102", "example", text="Original", translation="机译", translation_provider="libretranslate"),
                Post("103", "example"),
            ]
            for index, post in enumerate(posts):
                target = tmp_path / "preview.html"
                target.write_text(template.render(data=view_model(post)), encoding="utf-8")
                page.goto(target.resolve().as_uri())
                page.wait_for_function("window.twitterCardReady === true")
                assert page.evaluate("document.documentElement.scrollWidth") == 1080
                if index < 2:
                    assert page.locator("#translation-label").text_content() == "LLM 翻译"
                    assert page.locator("#translation-box").is_visible()
                if index == 0:
                    assert page.locator("#quote-translation-label").text_content() == "LLM 翻译"
                elif index == 1:
                    assert page.locator("#translation-note").text_content() == post.translation_note
                    assert "完整内容" in page.locator("#body").text_content()
                elif index == 2:
                    assert page.locator("#translation-label").text_content() == "LibreTranslate 翻译"
                else:
                    assert page.locator("#translation-box").is_hidden()
                page.locator(".twitter-page").screenshot(path=str(tmp_path / f"card-{index}.png"))
        finally:
            browser.close()
