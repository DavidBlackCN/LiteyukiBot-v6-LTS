import os
from pathlib import Path
from typing import Any

import aiofiles
import nonebot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from nonebot import require

require("nonebot_plugin_htmlrender")

from nonebot_plugin_htmlrender import (
    get_default_application,
    render_markdown,
    render_template,
    render_template_html,
)

from .tools import random_hex_string


async def md_to_pic(
    md: str = "",
    md_path: str = "",
    css_path: str = "",
    width: int = 500,
    device_scale_factor: float = 2,
    **kwargs: Any,
) -> bytes:
    """Render Markdown through htmlrender 0.8 while keeping the v6 API."""
    device_pixel_ratio = kwargs.pop("device_pixel_ratio", device_scale_factor)
    markdown_path = kwargs.pop("markdown_path", md_path)
    height = kwargs.pop("height", None)
    timeout_seconds = kwargs.pop("timeout_seconds", None)
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise TypeError(f"Unexpected md_to_pic arguments: {unexpected}")

    image = await render_markdown(
        markdown=md,
        markdown_path=markdown_path,
        css_path=css_path,
        width=width,
        height=height,
        device_pixel_ratio=device_pixel_ratio,
        timeout_seconds=timeout_seconds,
    )
    return bytes(image)


async def template2html(
    template: str,
    templates: dict,
) -> str:
    """
    Args:
        template: str: 模板文件
        templates: dict: 模板参数
    Returns:
        HTML 正文
    """
    template_path = os.path.dirname(template)
    template_name = os.path.basename(template)
    html = await render_template_html(
        template_path=template_path,
        template_name=template_name,
        variables=templates,
    )
    return str(html)


async def template2image(
    template: str,
    templates: dict,
    pages=None,
    wait: int = 0,
    scale_factor: float = 1,
    debug: bool = False,
) -> bytes:
    """
    template -> html -> image
    Args:
        debug: 输出渲染好的 html
        wait: 兼容旧 API；正值作为渲染超时秒数
        pages: 兼容旧 Playwright 页面参数；读取 viewport 宽高
        template: str: 模板文件
        templates: dict: 模板参数
        scale_factor: 缩放因子，越高越清晰
    Returns:
        图片二进制数据
    """
    viewport = (pages or {}).get("viewport", {})
    width = int(viewport.get("width", 1080))
    height = viewport.get("height")
    # Liteyuki historically used a 10px initial viewport and full-page capture.
    if height == 10:
        height = None

    template_path = os.path.dirname(template)
    template_name = os.path.basename(template)

    if debug:
        raw_html = await template2html(template, templates)
        random_file_name = f"debug-{random_hex_string(6)}.html"
        async with aiofiles.open(
            os.path.join(template_path, random_file_name), "w", encoding="utf-8"
        ) as file:
            await file.write(raw_html)
        nonebot.logger.info("生成调试用 HTML 文件于 `%s`" % random_file_name)

    image = await render_template(
        template_path=template_path,
        template_name=template_name,
        variables=templates,
        width=width,
        height=int(height) if height is not None else None,
        device_pixel_ratio=scale_factor,
        timeout_seconds=float(wait) if wait > 0 else None,
    )
    return bytes(image)


async def template2image_element(
    template: str,
    templates: dict,
    selector: str,
    *,
    pages: dict | None = None,
    wait_for: str | None = None,
    wait_timeout: int = 1000,
    scale_factor: float = 1,
) -> bytes:
    """Render one template element through htmlrender's Playwright provider."""
    if pages is None:
        pages = {"viewport": {"width": 1080, "height": 10}}

    html = await template2html(template, templates)
    application = get_default_application()
    async with application.extensions.playwright.page(
        device_scale_factor=scale_factor, **pages
    ) as page:
        page.on(
            "console",
            lambda message: nonebot.logger.debug(
                f"Browser console: {message.type}: {message.text}"
            ),
        )
        template_url = Path(template).resolve().as_uri()
        await page.route(
            template_url,
            lambda route: route.fulfill(
                status=200,
                body=html,
                content_type="text/html",
            ),
        )
        # Keep the template file URL as the document base so its relative
        # styles, scripts and images resolve exactly as they did in v6.
        await page.goto(template_url, wait_until="networkidle")
        if wait_for:
            try:
                await page.wait_for_function(wait_for, timeout=wait_timeout)
            except PlaywrightTimeoutError:
                nonebot.logger.debug(
                    f"Element render wait timed out after {wait_timeout}ms: {wait_for}"
                )
        return await page.locator(selector).screenshot(type="png")
