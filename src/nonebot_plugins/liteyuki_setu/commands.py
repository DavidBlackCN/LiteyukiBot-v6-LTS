from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from arclet.alconna import Alconna, Args, MultiVar
from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import Arparma, UniMessage, on_alconna

from .models import NoResultError, SetuError, UnsafeQueryError
from .parser import is_r18_request, parse_query
from .quota import get_private_r18_access, has_quota, record_success
from .recall import schedule_recall
from .service import cooldown, fetch_and_download, metadata_text
from .storage import default_settings, get_group_settings, group_allowed


def _raw_args(result: Arparma) -> str:
    return " ".join(str(value) for value in result.main_args.get("raw", [])).strip()


def _receipt_message_ids(receipt: Any) -> list[Any]:
    """Return usable message IDs from a UniMessage receipt."""
    message_ids = getattr(receipt, "msg_ids", None)
    if not message_ids:
        return []
    if isinstance(message_ids, (str, bytes)):
        message_ids = [message_ids]
    try:
        return [message_id for message_id in message_ids
                if message_id is not None and str(message_id).strip()]
    except TypeError:
        return []


def _is_superuser(bot: Any, event: Any) -> bool:
    return str(getattr(event, "user_id", "")) in {str(item) for item in getattr(bot.config, "superusers", set())}


async def _access_allowed(event: Any, is_superuser: bool) -> bool:
    try:
        from src.nonebot_plugins.liteyuki_access_control.api import is_allowed
        return await is_allowed("liteyuki_setu", str(getattr(event, "user_id", "")),
                                str(getattr(event, "group_id", "")) or None,
                                is_superuser=is_superuser)
    except Exception as exc:
        logger.warning(f"二次元图片访问控制检查失败，拒绝本次请求: {exc!r}")
        return False


setu_command = on_alconna(
    Alconna("色图", Args["raw", MultiVar(str), []]),
    aliases={"setu", "涩图", "来点色图", "来张色图", "二次元图"}, priority=20, block=True,
)


@setu_command.handle()
async def handle_setu(
    result: Arparma,
    event: Event,
    bot: Bot,
    matcher: Matcher,
):
    from . import config

    raw_args = _raw_args(result)
    r18_requested = is_r18_request(raw_args)
    group_id = getattr(event, "group_id", None)
    user_id = str(getattr(event, "user_id", ""))
    is_superuser = _is_superuser(bot, event)
    if not await _access_allowed(event, is_superuser):
        return
    if group_id is not None:
        if not group_allowed(config, group_id):
            return
        if r18_requested:
            await matcher.finish("R18 内容仅限已授权私聊使用喵~")
            return
        group_key = str(group_id)
        settings = get_group_settings(group_key, config)
        if not settings.enabled:
            await matcher.finish("本群未开启此功能喵~")
            return
        r18_allowed = False
    else:
        group_key = None
        if not config.setu_private_enabled:
            await matcher.finish("私聊未开启此功能喵~")
            return
        settings = default_settings(config)
        access = get_private_r18_access(config)
        r18_allowed = r18_requested and access.enabled and user_id in access.allowed_user_ids
        if r18_requested and not r18_allowed:
            await matcher.finish("你不准使用 R18 功能喵！")
            return
    try:
        query = parse_query(raw_args, default_count=settings.default_count,
                            max_count=config.setu_max_count, default_provider=settings.provider,
                            default_size=config.setu_image_size,
                            default_exclude_ai=settings.exclude_ai, allow_r18=r18_allowed)
    except (UnsafeQueryError, SetuError) as exc:
        await matcher.finish(str(exc))
        return
    key = f"{user_id}:{group_key or 'private'}"
    bypass = is_superuser and config.setu_superuser_bypass_cooldown
    if not cooldown.reserve(key, settings.cooldown_seconds, bypass):
        await matcher.finish("你冲的太快了喵，请稍后再试喵！")
        return
    sent = False
    sent_count = 0
    quota_date = datetime.now(ZoneInfo(config.setu_daily_limit_timezone)).date().isoformat()
    try:
        if group_key and not has_quota(group_key, user_id, quota_date,
                                       limit=settings.daily_image_limit_per_user,
                                       requested=query.count):
            await matcher.finish(f"别再冲了喵！本群每人每日最多获取 {settings.daily_image_limit_per_user} 张喵！")
            return
        downloaded = await fetch_and_download(query, config)
        if not downloaded:
            await matcher.finish("图片下载失败，请稍后再试喵~")
            return
        attempted_count = 0
        for position, (image, raw) in enumerate(downloaded):
            message = UniMessage.image(raw=raw)
            if config.setu_show_metadata:
                message = UniMessage.text(metadata_text(image)) + message
            attempted_count += 1
            try:
                receipt = await matcher.send(message)
            except Exception as exc:
                logger.warning(f"色图发送[{position + 1}/{query.count}]失败: pid={image.pid}, reason={exc!r}")
                continue
            message_ids = _receipt_message_ids(receipt)
            if not message_ids:
                logger.warning(f"色图发送[{position + 1}/{query.count}]未取得有效回执: "
                               f"pid={image.pid}, msg_ids={getattr(receipt, 'msg_ids', None)!r}")
                continue
            logger.info(f"色图发送[{position + 1}/{query.count}]: "
                        f"pid={image.pid}, message_ids={message_ids}")
            sent = True
            sent_count += 1
            if group_key:
                record_success(group_key, user_id, quota_date)
            if settings.auto_recall:
                schedule_recall(receipt, settings.recall_seconds)
            if position + 1 < len(downloaded):
                await asyncio.sleep(config.setu_send_interval_seconds)
        if sent_count < query.count:
            await matcher.send(f"本次仅成功获取 {sent_count}/{query.count} 张图片喵~")
        logger.info(f"色图发送完成: requested={query.count} attempted={attempted_count} "
                    f"confirmed={sent_count}")
    except NoResultError as exc:
        await matcher.finish(str(exc))
    except SetuError as exc:
        await matcher.finish(str(exc))
    finally:
        cooldown.finish(key, sent)