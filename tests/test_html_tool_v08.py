"""Compatibility tests for Liteyuki's htmlrender 0.8 adapter."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_html_tool_maps_legacy_arguments_and_artifacts() -> None:
    source = textwrap.dedent(
        """
        import asyncio
        from types import SimpleNamespace

        import nonebot
        import liteyuki.utils

        liteyuki.utils.IS_MAIN_PROCESS = False
        from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

        nonebot.init(render={"provider": "playwright", "startup": "off"})
        starter._load_htmlrender_plugin()
        from src.utils.message import html_tool

        calls = {}

        class ImageArtifact:
            def __bytes__(self):
                return b"image-bytes"

        class HtmlArtifact:
            def __str__(self):
                return "<main>rendered</main>"

        async def fake_markdown(**kwargs):
            calls["markdown"] = kwargs
            return ImageArtifact()

        async def fake_template_html(**kwargs):
            calls["template_html"] = kwargs
            return HtmlArtifact()

        async def fake_template(**kwargs):
            calls["template"] = kwargs
            return ImageArtifact()

        html_tool.render_markdown = fake_markdown
        html_tool.render_template_html = fake_template_html
        html_tool.render_template = fake_template

        assert asyncio.run(
            html_tool.md_to_pic("# title", width=540, device_scale_factor=4)
        ) == b"image-bytes"
        assert calls["markdown"]["markdown"] == "# title"
        assert calls["markdown"]["width"] == 540
        assert calls["markdown"]["device_pixel_ratio"] == 4

        assert asyncio.run(
            html_tool.template2html("templates/card.html", {"name": "Liteyuki"})
        ) == "<main>rendered</main>"
        assert calls["template_html"]["variables"] == {"name": "Liteyuki"}

        assert asyncio.run(
            html_tool.template2image(
                "templates/card.html",
                {"name": "Liteyuki"},
                pages={"viewport": {"width": 1080, "height": 10}},
                scale_factor=2,
                wait=5,
            )
        ) == b"image-bytes"
        assert calls["template"]["variables"] == {"name": "Liteyuki"}
        assert calls["template"]["width"] == 1080
        assert calls["template"]["height"] is None
        assert calls["template"]["device_pixel_ratio"] == 2
        assert calls["template"]["timeout_seconds"] == 5.0

        class Locator:
            async def screenshot(self, **kwargs):
                calls["screenshot"] = kwargs
                return b"element-bytes"

        class Page:
            def on(self, *args):
                calls["console"] = args[0]

            async def route(self, url, handler):
                calls["route"] = (url, handler)

            async def goto(self, url, **kwargs):
                calls["goto"] = (url, kwargs)

            async def wait_for_function(self, expression, **kwargs):
                calls["wait"] = (expression, kwargs)

            def locator(self, selector):
                calls["selector"] = selector
                return Locator()

        class PageContext:
            async def __aenter__(self):
                return Page()

            async def __aexit__(self, *args):
                return None

        class PlaywrightAccess:
            def page(self, **kwargs):
                calls["page"] = kwargs
                return PageContext()

        application = SimpleNamespace(
            extensions=SimpleNamespace(playwright=PlaywrightAccess())
        )
        html_tool.get_default_application = lambda: application

        result = asyncio.run(
            html_tool.template2image_element(
                "templates/card.html",
                {"name": "Liteyuki"},
                "#card",
                pages={"viewport": {"width": 640, "height": 100}},
                wait_for="window.ready === true",
                wait_timeout=2500,
                scale_factor=3,
            )
        )
        assert result == b"element-bytes"
        assert calls["page"] == {
            "device_scale_factor": 3,
            "viewport": {"width": 640, "height": 100},
        }
        assert calls["route"][0].endswith("/templates/card.html")
        assert calls["goto"][0] == calls["route"][0]
        assert calls["goto"][1] == {"wait_until": "networkidle"}
        assert calls["wait"] == ("window.ready === true", {"timeout": 2500})
        assert calls["selector"] == "#card"
        """
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
