"""Command handlers for /ks and /komari-status."""

from datetime import datetime, timezone

from nonebot import on_command
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    MessageEvent,
    MessageSegment,
)

from .config import get_config
from .renderer import render_status


komari_status = on_command("ks", aliases={"komari-status"}, priority=5, block=True)

_last_sent: dict[int, datetime] = {}


@komari_status.handle()
async def _handle_komari_status(event: MessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        await komari_status.finish("请到群聊中使用该命令")

    config = get_config()

    if (
        config.komari_group_allowlist
        and event.group_id not in config.komari_group_allowlist
    ):
        await komari_status.finish("该群未在命令白名单中")

    now = datetime.now(timezone.utc)
    last = _last_sent.get(event.group_id)
    if last is not None:
        elapsed = (now - last).total_seconds()
        if elapsed < config.komari_cooldown_seconds:
            wait_seconds = int(config.komari_cooldown_seconds - elapsed) + 1
            await komari_status.finish(f"操作太频繁，请 {wait_seconds} 秒后再试")
    _last_sent[event.group_id] = now

    try:
        image = await render_status(config)
    except Exception as exc:  # noqa: BLE001
        _last_sent.pop(event.group_id, None)
        await komari_status.finish(f"获取探针截图失败：{exc}")

    await komari_status.finish(MessageSegment.image(image))
