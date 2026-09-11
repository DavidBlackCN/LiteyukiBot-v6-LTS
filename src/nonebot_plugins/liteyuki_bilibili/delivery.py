"""Adapter-capability-aware text delivery used before card rendering is added."""

from __future__ import annotations

import nonebot

from .models import BilibiliEvent, BilibiliSubscription


def choose_push_bot():
    bots = nonebot.get_bots()
    if len(bots) == 1:
        return next(iter(bots.values()))
    if not bots:
        nonebot.logger.warning("Bilibili 推送跳过：当前没有已连接 Bot")
    else:
        nonebot.logger.warning("Bilibili 推送跳过：存在多个 Bot，暂不能确定推送账号")
    return None


def event_text(event: BilibiliEvent) -> str:
    labels = {
        "dynamic": "动态更新",
        "video": "发布了新视频",
        "live_start": "开始直播",
        "live_end": "结束直播",
    }
    author = event.author_name or f"UP {event.uid}"
    lines = [f"Bilibili {labels[event.kind]}｜{author}"]
    if event.title:
        lines.append(event.title)
    if event.body:
        lines.append(event.body[:500])
    if event.url:
        lines.append(event.url)
    return "\n".join(lines)


async def deliver_text(subscription: BilibiliSubscription, event: BilibiliEvent) -> bool:
    """Send plain text through the available OneBot V11/V12 capability."""
    bot = choose_push_bot()
    if bot is None:
        return False
    content = event_text(event)
    try:
        if subscription.target_type == "group" and hasattr(bot, "send_group_msg"):
            await bot.send_group_msg(group_id=int(subscription.target_id), message=content)
        elif subscription.target_type == "private" and hasattr(bot, "send_private_msg"):
            await bot.send_private_msg(user_id=int(subscription.target_id), message=content)
        elif subscription.target_type == "group":
            await bot.call_api(
                "send_message",
                detail_type="group",
                group_id=str(subscription.target_id),
                message=[{"type": "text", "data": {"text": content}}],
            )
        else:
            await bot.call_api(
                "send_message",
                detail_type="private",
                user_id=str(subscription.target_id),
                message=[{"type": "text", "data": {"text": content}}],
            )
    except Exception as exc:
        nonebot.logger.warning(
            "Bilibili 文本推送失败: target=%s:%s error=%r",
            subscription.target_type,
            subscription.target_id,
            exc,
        )
        return False
    return True
