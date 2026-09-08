import asyncio
from contextlib import suppress

from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import event_postprocessor, run_preprocessor
from nonebot.permission import SUPERUSER

from .api import config, controller


def context_ids(matcher, event):
    plugin = getattr(matcher, "plugin", None)
    name = getattr(plugin, "name", None)
    try:
        user = str(event.get_user_id())
    except (AttributeError, ValueError, NotImplementedError):
        user = None
    group = getattr(event, "group_id", None)
    return name, user, str(group) if group is not None else None


# Retain events only until event_postprocessor; one event consumes one quota
# per plugin, even when that plugin has multiple matching handlers.
_decisions = {}
_cleanup_task = None


@run_preprocessor
async def guard(bot: Bot, event: Event, matcher: Matcher):
    if not config.access_control_enabled or event.get_type() != "message":
        return
    plugin, user, group = context_ids(matcher, event)
    if not plugin:
        return
    superuser = await SUPERUSER(bot, event)
    key = (id(bot), id(event))
    cache = _decisions.setdefault(key, (event, {}))[1]
    if plugin not in cache:
        if not controller.allowed(plugin, user, group, superuser=superuser):
            reason = "访问被拒绝"
        elif not controller.rate_allowed(plugin, user, group, superuser=superuser):
            reason = "调用过于频繁，请稍后重试"
        else:
            reason = None
        cache[plugin] = reason
        # One response per event prevents spam from multiple denied plugins.
        reply = config.access_control_reply_on_denied if reason == "访问被拒绝" else config.access_control_reply_on_rate_limited
        if reason and reply and "__notified__" not in cache:
            cache["__notified__"] = True
            try:
                await bot.send(event, f"{plugin}：{reason}")
            except Exception as error:
                logger.debug(f"访问控制提示发送失败：{error}")
    if cache[plugin]:
        raise IgnoredException(cache[plugin])


@event_postprocessor
async def clear_decisions(bot: Bot, event: Event):
    _decisions.pop((id(bot), id(event)), None)


async def cleanup_loop():
    while True:
        await asyncio.sleep(60)
        controller.cleanup()


@get_driver().on_startup
async def start_cleanup():
    global _cleanup_task
    _cleanup_task = asyncio.create_task(cleanup_loop())


@get_driver().on_shutdown
async def stop_cleanup():
    if _cleanup_task:
        _cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await _cleanup_task
    _decisions.clear()
