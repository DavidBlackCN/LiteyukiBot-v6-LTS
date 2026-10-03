"""Offline layout checks using an existing Chromium; never download browsers."""
import base64
import os
import shutil
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright


def _image(width=160, height=90):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="pink"/></svg>'
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def test_gallery_decodes_template_images_and_preserves_complete_content(tmp_path, monkeypatch):
    local = os.environ.get("LOCALAPPDATA")
    cache = Path(local) / "nonebot2/nonebot_plugin_htmlrender" if local else None
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH") and cache and cache.exists():
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(cache))
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("No existing Chromium executable; browser download is intentionally disabled")
        browser = playwright.chromium.launch()
        try:
            for pack in ("vanilla_resource", "liteyuki_bilibili"):
                shutil.copytree(Path("src/resources") / pack / "templates", tmp_path, dirs_exist_ok=True)
            environment = Environment(loader=FileSystemLoader(tmp_path), autoescape=True)
            template = environment.get_template("bilibili_dynamic.html")
            page = browser.new_page(viewport={"width":1080,"height":10})
            data = {"label":"动态", "author":"测试作者", "title":"测试标题", "avatar":"", "metrics":[],
                    "body":"<script>window.injected=true</script>" + "完整正文" * 500,
                    "display_type":"dynamic", "url":"https://t.bilibili.com/123"}
            for count, rows in ((1,1), (2,1), (3,1), (4,2), (5,2), (9,3)):
                data["covers"] = [_image()] * count
                target = tmp_path / "preview.html"
                target.write_text(template.render(data=data), encoding="utf-8")
                page.goto(target.resolve().as_uri())
                page.wait_for_function("window.bilibiliCardReady === true")
                assert page.locator("#covers img").count() == count
                assert page.locator("#covers .cover-row").count() == rows
                assert page.locator("#body").text_content() == data["body"]
                assert not page.evaluate("!!window.injected")
                assert page.evaluate("document.documentElement.scrollWidth") == 1080
                assert page.locator("#metrics").is_hidden()
                assert page.locator("#timestamp").is_hidden()
                last = page.locator("#covers .cover-row").last
                widths = last.locator("img").evaluate_all("nodes => nodes.map(n => n.getBoundingClientRect().width)")
                assert sum(widths) + (len(widths)-1)*14 == pytest.approx(last.bounding_box()["width"], abs=1)
            data.update(covers=[_image(), _image(100,400), "data:image/png;base64,broken"],
                        original={"author_name":"原作者", "title":"原标题", "body":"原文", "covers":[_image()], "url":"", "unavailable":False})
            target.write_text(template.render(data=data), encoding="utf-8")
            page.reload()
            page.wait_for_function("window.bilibiliCardReady === true")
            assert page.locator("#covers img").count() == 2
            vertical = page.locator("#covers > img")
            assert vertical.count() == 1
            box = vertical.bounding_box()
            assert (box["height"] - 2) / (box["width"] - 2) == pytest.approx(4)
            assert page.locator("#original-covers img").count() == 1
            assert page.locator("#original-body").text_content() == "原文"
            data["covers"] = []
            data["original"]["unavailable"] = True
            target.write_text(template.render(data=data), encoding="utf-8")
            page.reload()
            page.wait_for_function("window.bilibiliCardReady === true")
            assert page.locator("#covers").is_hidden()
            assert page.locator("#original-covers img").count() == 0
            assert "已失效" in page.locator("#original-title").text_content()
        finally:
            browser.close()
