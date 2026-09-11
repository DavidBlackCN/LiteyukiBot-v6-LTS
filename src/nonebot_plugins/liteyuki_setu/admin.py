from __future__ import annotations

from typing import Any

from arclet.alconna import Alconna, Args, MultiVar
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import Arparma, on_alconna

from src.nonebot_plugins.liteyuki_group_manager.permission import ADMIN, is_superuser

from .quota import (add_private_r18_user, get_private_r18_access,
                    remove_private_r18_user, set_private_r18_enabled)
from .storage import get_group_settings, reset_group_settings, update_group_settings


def _tokens(result: Arparma) -> list[str]:
    return [str(value).strip() for value in result.main_args.get("raw", []) if str(value).strip()]


def _status(settings: Any) -> str:
    daily = "不限" if settings.daily_image_limit_per_user == 0 else f"{settings.daily_image_limit_per_user} 张"
    return (f"状态：{'开启' if settings.enabled else '关闭'}\n"
            f"自动撤回：{'开' if settings.auto_recall else '关'}（{settings.recall_seconds} 秒）\n"
            f"默认数量：{settings.default_count}\n来源：{settings.provider}\n"
            f"AI 过滤：{'开' if settings.exclude_ai else '关'}\n冷却：{settings.cooldown_seconds} 秒\n"
            f"每人每日图片额度：{daily}")


async def _handle_private_r18(args: list[str], config, matcher) -> None:
    action = args[1] if len(args) > 1 else "状态"
    if action == "状态":
        access = get_private_r18_access(config)
        users = "、".join(sorted(access.allowed_user_ids)) or "无"
        await matcher.finish(f"私聊 R18：{'开启' if access.enabled else '关闭'}\n授权 QQ：{users}")
    elif action in {"开", "关"}:
        set_private_r18_enabled(action == "开", config)
        await matcher.finish(f"私聊 R18 已{'开启' if action == '开' else '关闭'}。")
    elif action in {"添加", "移除"} and len(args) >= 3 and args[2].isdigit():
        if action == "添加":
            add_private_r18_user(args[2], config)
            await matcher.finish("已添加私聊 R18 授权 QQ。")
        else:
            remove_private_r18_user(args[2], config)
            await matcher.finish("已移除私聊 R18 动态授权 QQ。")
    else:
        await matcher.finish("用法：色图管理 私聊R18 状态|开|关|添加 <QQ>|移除 <QQ>")


setu_admin = on_alconna(
    Alconna("色图管理", Args["raw", MultiVar(str), []]),
    aliases={"图片管理", "setu-admin"}, permission=ADMIN, priority=20, block=True,
)


@setu_admin.handle()
async def handle_admin(
    result: Arparma,
    event: Event,
    bot: Bot,
    matcher: Matcher,
):
    from . import config

    args = _tokens(result)
    if not args:
        await matcher.finish("用法：色图管理 状态|开启|关闭|撤回|数量|来源|AI过滤|冷却|日限|重置；私聊R18 管理仅限超级用户")
        return
    superuser = await is_superuser(bot, event)
    if args[0] in {"私聊R18", "R18"}:
        if not superuser:
            await matcher.finish("权限不足，仅超级用户可管理私聊 R18。")
            return
        await _handle_private_r18(args, config, matcher)
        return
    group_id = getattr(event, "group_id", None)
    if group_id is None:
        if args[:2] in (["私聊", "开"], ["私聊", "关"]):
            await matcher.finish("私聊开关请通过 setu_private_enabled 配置后重启生效。" if superuser else "权限不足，仅超级用户可执行此操作。")
            return
        await matcher.finish("该管理命令只能在群聊中使用。")
        return
    target, action = str(group_id), args[0]
    if superuser and action in {"状态", "开启", "关闭", "重置"} and len(args) > 1 and args[1].isdigit():
        target = args[1]
    if superuser and action == "日限" and len(args) > 2 and args[2].isdigit():
        target = args[2]
    if action == "状态":
        await matcher.finish(_status(get_group_settings(target, config)))
    elif action in {"开启", "关闭"}:
        update_group_settings(target, config, enabled=action == "开启")
        await matcher.finish(f"已{'开启' if action == '开启' else '关闭'}本群全年龄图片功能。")
    elif action == "重置":
        reset_group_settings(target, config)
        await matcher.finish("已重置本群色图设置。")
    elif action == "撤回" and len(args) >= 2 and args[1] in {"开", "关"}:
        update_group_settings(target, config, auto_recall=args[1] == "开")
        await matcher.finish(f"自动撤回已{'开启' if args[1] == '开' else '关闭'}。")
    elif action == "撤回时间" and len(args) >= 2 and args[1].isdigit():
        seconds = int(args[1])
        if not 5 <= seconds <= 600:
            await matcher.finish("撤回时间必须在 5 到 600 秒之间。")
        else:
            update_group_settings(target, config, recall_seconds=seconds)
            await matcher.finish("撤回时间已更新。")
    elif action == "数量" and len(args) >= 2 and args[1].isdigit():
        count = int(args[1])
        if not 1 <= count <= config.setu_max_count:
            await matcher.finish(f"数量必须在 1 到 {config.setu_max_count} 之间。")
        else:
            update_group_settings(target, config, default_count=count)
            await matcher.finish("默认数量已更新。")
    elif action == "来源" and len(args) >= 2 and args[1] in {"auto", "lolicon", "mirlkoi"}:
        update_group_settings(target, config, provider=args[1])
        await matcher.finish("默认图片源已更新。")
    elif action == "AI过滤" and len(args) >= 2 and args[1] in {"开", "关"}:
        update_group_settings(target, config, exclude_ai=args[1] == "开")
        await matcher.finish("AI 过滤设置已更新。")
    elif action == "冷却" and len(args) >= 2 and args[1].isdigit():
        seconds = int(args[1])
        if not 0 <= seconds <= 3600:
            await matcher.finish("冷却时间必须在 0 到 3600 秒之间。")
        else:
            update_group_settings(target, config, cooldown_seconds=seconds)
            await matcher.finish("冷却时间已更新。")
    elif action == "日限" and len(args) >= 2 and args[1].isdigit():
        limit = int(args[1])
        if not 0 <= limit <= 1000:
            await matcher.finish("每日额度必须在 0 到 1000 张之间。")
        else:
            update_group_settings(target, config, daily_image_limit_per_user=limit)
            await matcher.finish("每日图片额度已更新。")
    else:
        await matcher.finish("参数不正确，请使用：状态、开启、关闭、撤回、撤回时间、数量、来源、AI过滤、冷却、日限或重置。")