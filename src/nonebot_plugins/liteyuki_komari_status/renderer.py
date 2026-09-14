"""Render the Komari dashboard through Liteyuki's shared htmlrender browser."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING

from nonebot.log import logger

from src.utils.message.html_tool import _render_slot
from nonebot_plugin_htmlrender import get_default_application

if TYPE_CHECKING:
    from playwright.async_api import Page

from .config import Config
from .errors import LoginFailedError, RenderTimeoutError


async def render_status(config: Config) -> str:
    """Return a OneBot-friendly base64 image string."""
    context_kwargs: dict = {
        "viewport": {
            "width": config.komari_screenshot_width,
            "height": config.komari_screenshot_height,
        },
        "device_scale_factor": config.komari_device_scale_factor,
    }

    if config.komari_storage_state_path:
        storage_path = Path(config.komari_storage_state_path)
        if storage_path.exists():
            context_kwargs["storage_state"] = str(storage_path)

    async with _render_slot():
        application = get_default_application()
        async with application.extensions.playwright.browser() as browser:
            context = await browser.new_context(**context_kwargs)
            page: Page | None = None
            try:
                page = await context.new_page()
                await _goto_and_wait(page, config)
                await _maybe_login(page, config)
                await _wait_for_ready(page, config)

                # Give charts a moment to finish drawing.
                await page.wait_for_timeout(config.komari_render_delay_ms)

                raw = await page.screenshot(
                    type=config.komari_screenshot_type,
                    quality=(
                        config.komari_screenshot_quality
                        if config.komari_screenshot_type == "jpeg"
                        else None
                    ),
                    full_page=False,
                )

                if config.komari_storage_state_path and config.komari_username:
                    await context.storage_state(path=config.komari_storage_state_path)

                return "base64://" + base64.b64encode(raw).decode()
            except LoginFailedError:
                raise
            except Exception as exc:
                raise RenderTimeoutError(f"渲染 Komari 页面失败: {exc}") from exc
            finally:
                try:
                    if page is not None:
                        await page.close()
                finally:
                    await context.close()


async def _goto_and_wait(page: Page, config: Config) -> None:
    try:
        await page.goto(
            config.komari_url,
            wait_until="load",
            timeout=config.komari_wait_timeout,
        )
        if config.komari_wait_networkidle:
            try:
                await page.wait_for_load_state(
                    "networkidle",
                    timeout=config.komari_networkidle_timeout,
                )
            except TimeoutError:
                # Some dashboards keep polling; let the selector/delay finish.
                pass
        await page.wait_for_selector(
            config.komari_wait_selector,
            timeout=config.komari_wait_timeout,
        )
    except Exception as exc:
        raise RenderTimeoutError(
            f"加载超时或找不到元素 {config.komari_wait_selector!r}: {exc}"
        ) from exc


async def _wait_for_ready(page: Page, config: Config) -> None:
    """Wait until configured dashboard readiness signals have settled."""
    selector = config.komari_ready_selector or ""
    min_count = max(1, config.komari_ready_min_count)
    url = config.komari_background_url or ""
    text = config.komari_loading_text or ""
    if not selector and not url and not text:
        return

    try:
        await page.wait_for_function(
            """({ selector, minCount, url, text, timeout }) => new Promise((resolve) => {
                const started = Date.now();
                const check = () => {
                    const nodesReady = !selector
                        || document.querySelectorAll(selector).length >= minCount;
                    const backgroundLoaded = !url || performance
                        .getEntriesByType("resource")
                        .some((entry) => entry.name.includes(url));
                    const textGone = !text || !document.body.innerText.includes(text);
                    if (
                        (nodesReady && backgroundLoaded && textGone)
                        || Date.now() - started >= timeout
                    ) {
                        resolve(true);
                    } else {
                        setTimeout(check, 200);
                    }
                };
                check();
            })""",
            arg={
                "selector": selector,
                "minCount": min_count,
                "url": url,
                "text": text,
                "timeout": config.komari_wait_timeout,
            },
            timeout=config.komari_wait_timeout + 1000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("等待页面加载完成超时，继续截图: {}", exc)


async def _maybe_login(page: Page, config: Config) -> None:
    if not config.komari_username or not config.komari_password:
        return

    password_input = page.locator("input[type='password']").first
    if await password_input.count() == 0:
        return

    try:
        username_input = page.locator(
            "input[type='text'], input[name='username'], input[name='email'], input[name='account']"
        ).first
        await username_input.fill(config.komari_username)
        await password_input.fill(config.komari_password)
        await password_input.press("Enter")
        await page.wait_for_load_state("load", timeout=config.komari_wait_timeout)
        await page.wait_for_timeout(500)
        if await page.locator("input[type='password']").count() > 0:
            raise LoginFailedError("登录失败：页面仍存在密码输入框")
    except LoginFailedError:
        raise
    except Exception as exc:
        raise LoginFailedError(f"自动登录失败: {exc}") from exc
