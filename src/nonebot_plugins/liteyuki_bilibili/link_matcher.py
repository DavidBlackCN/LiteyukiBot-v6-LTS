"""The single built-in Bilibili link matcher, enabled after legacy retirement."""

from __future__ import annotations

from nonebot import logger, on_message
from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import UniMessage

from .delivery import event_text
from .errors import BilibiliError
from .parser import BilibiliLinkParser, resolve_links
from .runtime import get_client


bilibili_link = on_message(priority=90, block=False)


@bilibili_link.handle()
async def handle_bilibili_link(event: Event, matcher: Matcher) -> None:
    from . import config

    if not config.bilibili_enabled or not config.bilibili_link_parse_enabled:
        return
    text = event.get_plaintext()
    if not any(marker in text.lower() for marker in ("bv", "av", "bilibili.com", "b23.tv")):
        return
    try:
        client = get_client()
        await client.start()
        links = await resolve_links(text, client)
        parser = BilibiliLinkParser(client)
    except (BilibiliError, RuntimeError) as exc:
        logger.warning(f"Bilibili 链接解析准备失败: {exc!r}")
        return
    for link in links:
        try:
            item = await parser.parse(link)
        except (BilibiliError, RuntimeError, ValueError) as exc:
            logger.warning(f"Bilibili 链接解析失败: {link.kind}:{link.identifier} error={exc!r}")
            continue
        try:
            from .renderer import render_event_card

            image = await render_event_card(item, client, config.bilibili_render_scale)
        except Exception as exc:
            logger.warning(f"Bilibili 链接卡片渲染失败，改用文本: {exc!r}")
            await matcher.send(event_text(item))
            continue
        await UniMessage.image(raw=image).send()
