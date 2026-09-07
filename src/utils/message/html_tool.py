import os
from pathlib import Path

import aiofiles
import nonebot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from nonebot import require

require("nonebot_plugin_htmlrender")

from nonebot_plugin_htmlrender import (
    template_to_html,
    template_to_pic,
    md_to_pic,
    init,
)
from nonebot_plugin_htmlrender.browser import get_new_page

from .tools import random_hex_string

async def template2html(
    template: str,
    templates: dict,
) -> str:
    """
    Args:
        template: str: 模板文件
        **templates: dict: 模板参数
    Returns:
        HTML 正文
    """
    template_path = os.path.dirname(template)
    template_name = os.path.basename(template)
    return await template_to_html(template_path, template_name, **templates)


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
        debug: 输入渲染好的 html
        wait: 等待时间，单位秒
        pages: 页面参数
        template: str: 模板文件
        templates: dict: 模板参数
        scale_factor: 缩放因子，越高越清晰
    Returns:
        图片二进制数据
    """
    if pages is None:
        pages = {
            "viewport": {"width": 1080, "height": 10},
        }

    template_path = os.path.dirname(template)
    template_name = os.path.basename(template)

    if debug:
        # 重载资源
        raw_html = await template_to_html(
            template_name=template_name,
            template_path=template_path,
            **templates,
        )
        random_file_name = f"debug-{random_hex_string(6)}.html"
        async with aiofiles.open(
            os.path.join(template_path, random_file_name), "w", encoding="utf-8"
        ) as f:
            await f.write(raw_html)
        nonebot.logger.info("生成调试用 HTML 文件于 `%s`" % f"{random_file_name}")

    return await template_to_pic(
        template_name=template_name,
        template_path=template_path,
        templates=templates,
        wait=wait,
        ###
        pages=pages,
        device_scale_factor=scale_factor,
        ###
    )


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
    """Render one template element without changing the shared full-page path."""
    if pages is None:
        pages = {"viewport": {"width": 1080, "height": 10}}

    template_path = os.path.dirname(template)
    html = await template_to_html(
        template_path=template_path,
        template_name=os.path.basename(template),
        **templates,
    )
    async with get_new_page(scale_factor, **pages) as page:
        page.on(
            "console",
            lambda message: nonebot.logger.debug(
                f"Browser console: {message.type}: {message.text}"
            ),
        )
        await page.goto(Path(template_path).resolve().as_uri())
        await page.set_content(html, wait_until="networkidle")
        if wait_for:
            try:
                await page.wait_for_function(wait_for, timeout=wait_timeout)
            except PlaywrightTimeoutError:
                nonebot.logger.debug(
                    f"Element render wait timed out after {wait_timeout}ms: {wait_for}"
                )
        return await page.locator(selector).screenshot(type="png")
