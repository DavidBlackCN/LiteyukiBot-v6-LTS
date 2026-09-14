"""Regression coverage for the LTS Komari/htmlrender bridge."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = (
    PROJECT_ROOT / "src/nonebot_plugins/liteyuki_komari_status/renderer.py"
)


def test_komari_reuses_htmlrender_browser_and_releases_contexts() -> None:
    source = RENDERER_PATH.read_text(encoding="utf-8")
    assert "async_playwright" not in source
    assert ".chromium.launch(" not in source
    assert "get_default_application" in source

    test_source = textwrap.dedent(
        """
        import asyncio
        import base64
        import tempfile
        from contextlib import asynccontextmanager
        from pathlib import Path
        from types import SimpleNamespace

        import nonebot

        nonebot.init(render={"provider": "playwright", "startup": "off"})
        from src.nonebot_plugins.liteyuki_komari_status import renderer
        from src.nonebot_plugins.liteyuki_komari_status.errors import RenderTimeoutError

        calls = []

        @asynccontextmanager
        async def shared_render_slot():
            calls.append("slot-enter")
            try:
                yield
            finally:
                calls.append("slot-exit")

        class Locator:
            def __init__(self, page, selector):
                self.page = page
                self.selector = selector

            @property
            def first(self):
                return self

            async def count(self):
                if self.selector == "input[type='password']":
                    return int(self.page.password_visible)
                return 1

            async def fill(self, value):
                calls.append(("fill", self.selector, value))

            async def press(self, value):
                calls.append(("press", self.selector, value))
                self.page.password_visible = False

        class Page:
            def __init__(self, fail=False):
                self.fail = fail
                self.password_visible = True
                self.closed = False

            async def goto(self, url, **kwargs):
                calls.append(("goto", url, kwargs))
                if self.fail:
                    raise RuntimeError("unreachable")

            async def wait_for_load_state(self, state, **kwargs):
                calls.append(("load-state", state, kwargs))

            async def wait_for_selector(self, selector, **kwargs):
                calls.append(("selector", selector, kwargs))

            async def wait_for_function(self, script, **kwargs):
                calls.append(("ready", kwargs))

            async def wait_for_timeout(self, delay):
                calls.append(("delay", delay))

            async def screenshot(self, **kwargs):
                calls.append(("screenshot", kwargs))
                return b"komari-image"

            def locator(self, selector):
                return Locator(self, selector)

            async def close(self):
                self.closed = True
                calls.append("page-close")

        class Context:
            def __init__(self, page):
                self.page = page
                self.closed = False
                self.storage_path = None

            async def new_page(self):
                return self.page

            async def storage_state(self, *, path):
                self.storage_path = path
                calls.append(("storage-state", path))

            async def close(self):
                self.closed = True
                calls.append("context-close")

        class Browser:
            def __init__(self, contexts):
                self.contexts = contexts
                self.closed = False
                self.context_kwargs = []

            async def new_context(self, **kwargs):
                self.context_kwargs.append(kwargs)
                return self.contexts.pop(0)

            async def close(self):
                self.closed = True
                raise AssertionError("shared browser must not be closed")

        class BrowserLease:
            def __init__(self, browser):
                self.browser = browser
                self.entered = False
                self.exited = False

            async def __aenter__(self):
                self.entered = True
                return self.browser

            async def __aexit__(self, *args):
                self.exited = True

        with tempfile.TemporaryDirectory() as directory:
            storage_path = Path(directory) / "komari-storage.json"
            storage_path.write_text("{}", encoding="utf-8")
            config = SimpleNamespace(
                komari_url="http://komari.test",
                komari_username="admin",
                komari_password="secret",
                komari_storage_state_path=str(storage_path),
                komari_screenshot_width=1280,
                komari_screenshot_height=720,
                komari_device_scale_factor=1.5,
                komari_screenshot_type="jpeg",
                komari_screenshot_quality=85,
                komari_wait_selector="#dashboard",
                komari_wait_timeout=1000,
                komari_wait_networkidle=True,
                komari_networkidle_timeout=250,
                komari_ready_selector=".node",
                komari_ready_min_count=2,
                komari_background_url="background.png",
                komari_loading_text="Loading",
                komari_render_delay_ms=123,
            )
            page = Page()
            context = Context(page)
            browser = Browser([context])
            lease = BrowserLease(browser)
            application = SimpleNamespace(
                extensions=SimpleNamespace(
                    playwright=SimpleNamespace(browser=lambda: lease)
                )
            )
            renderer._render_slot = shared_render_slot
            renderer.get_default_application = lambda: application

            image = asyncio.run(renderer.render_status(config))
            assert image == "base64://" + base64.b64encode(b"komari-image").decode()
            assert browser.context_kwargs == [{
                "viewport": {"width": 1280, "height": 720},
                "device_scale_factor": 1.5,
                "storage_state": str(storage_path),
            }]
            assert context.storage_path == str(storage_path)
            assert page.closed and context.closed
            assert not browser.closed
            assert lease.entered and lease.exited
            assert calls[0:2] == ["slot-enter", ("goto", "http://komari.test", {
                "wait_until": "load", "timeout": 1000,
            })]
            assert ("load-state", "networkidle", {"timeout": 250}) in calls
            assert ("selector", "#dashboard", {"timeout": 1000}) in calls
            assert ("fill", "input[type='text'], input[name='username'], input[name='email'], input[name='account']", "admin") in calls
            assert ("fill", "input[type='password']", "secret") in calls
            assert ("press", "input[type='password']", "Enter") in calls
            assert ("delay", 123) in calls
            assert ("screenshot", {
                "type": "jpeg", "quality": 85, "full_page": False,
            }) in calls
            assert "page-close" in calls and "context-close" in calls
            assert calls[-1] == "slot-exit"

            failed_page = Page(fail=True)
            failed_context = Context(failed_page)
            failed_browser = Browser([failed_context])
            failed_lease = BrowserLease(failed_browser)
            renderer.get_default_application = lambda: SimpleNamespace(
                extensions=SimpleNamespace(
                    playwright=SimpleNamespace(browser=lambda: failed_lease)
                )
            )
            try:
                asyncio.run(renderer.render_status(config))
            except RenderTimeoutError:
                pass
            else:
                raise AssertionError("failed render did not raise RenderTimeoutError")
            assert failed_page.closed and failed_context.closed
            assert not failed_browser.closed
            assert failed_lease.entered and failed_lease.exited
        """
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", test_source],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
