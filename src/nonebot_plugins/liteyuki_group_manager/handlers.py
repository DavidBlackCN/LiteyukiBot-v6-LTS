from typing import Any

from nonebot import logger, on_command, on_type
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupDecreaseNoticeEvent,
    GroupIncreaseNoticeEvent,
    GroupMessageEvent,
    Message,
    MessageEvent,
)
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from .config import group_manager_config as config
from .permission import bot_admin_overrides
from .core import (
    ROLE_RANK,
    ban_member,
    delete_group_message,
    extract_reply_message_id,
    extract_target,
    format_notice,
    group_only_error,
    has_management_permission,
    has_owner_permission,
    kick_member,
    member_nickname,
    member_role,
    parse_duration,
    set_group_admin,
    set_whole_ban,
    validate_target,
)


ban = on_command("禁言", priority=10, block=True)
unban = on_command("解禁", priority=10, block=True)
kick = on_command("踢出", aliases={"踢人"}, priority=10, block=True)
recall = on_command("撤回", priority=10, block=True)
whole_ban = on_command("全员禁言", priority=10, block=True)
whole_unban = on_command("解除全员禁言", priority=10, block=True)
grant_admin = on_command("设置管理员", priority=10, block=True)
revoke_admin = on_command("取消管理员", priority=10, block=True)


def _is_superuser(bot: Bot, event: MessageEvent) -> bool:
    return str(event.user_id) in {str(user_id) for user_id in bot.config.superusers}


async def _finish_error(matcher: Any, message: str) -> None:
    await matcher.finish(message)


async def _group_event_or_finish(matcher: Any, event: MessageEvent) -> GroupMessageEvent:
    error = group_only_error(event)
    if error:
        await _finish_error(matcher, error)
    return event  # type: ignore[return-value]


async def _require_operator(
    matcher: Any,
    bot: Bot,
    event: GroupMessageEvent,
    owner_only: bool = False,
) -> bool:
    is_superuser = _is_superuser(bot, event)
    role = str(event.sender.role or "member")
    allowed = (
        has_owner_permission(role, is_superuser)
        if owner_only
        else has_management_permission(role, is_superuser)
    )
    if not allowed:
        await _finish_error(
            matcher,
            "权限不足，仅群管理员、群主或超级用户可执行此操作",
        )
    return is_superuser


async def _member_info(bot: Bot, group_id: int, user_id: int) -> dict[str, Any]:
    return await bot.get_group_member_info(
        group_id=group_id,
        user_id=user_id,
        no_cache=True,
    )


async def _validate_member_action(
    matcher: Any,
    bot: Bot,
    event: GroupMessageEvent,
    target_id: int,
    is_superuser: bool,
) -> None:
    try:
        bot_member = await _member_info(bot, event.group_id, int(bot.self_id))
        target_member = await _member_info(bot, event.group_id, target_id)
    except Exception as error:
        logger.warning(f"群管理成员信息查询失败: {error!r}")
        await _finish_error(matcher, "无法取得群成员权限信息，请稍后重试")
        return
    validation_error = validate_target(
        actor_role=str(event.sender.role or "member"),
        bot_role=member_role(bot_member),
        target_role=member_role(target_member),
        is_superuser=is_superuser,
        bot_id=int(bot.self_id),
        target_id=target_id,
    )
    if validation_error:
        await _finish_error(matcher, validation_error)


async def _run_action(matcher: Any, action: Any, success: str, failure: str) -> None:
    try:
        await action
    except Exception as error:
        logger.warning(f"{failure}: {error!r}")
        await _finish_error(matcher, failure)
        return
    await matcher.finish(success)


@ban.handle()
async def handle_ban(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
):
    group_event = await _group_event_or_finish(ban, event)
    is_superuser = await _require_operator(ban, bot, group_event)
    try:
        target_id = extract_target(args)
        duration = parse_duration(
            args.extract_plain_text(),
            config.group_manager_default_ban_seconds,
            config.group_manager_max_ban_seconds,
        )
    except ValueError as error:
        await ban.finish(str(error))
        return
    await _validate_member_action(ban, bot, group_event, target_id, is_superuser)
    await _run_action(
        ban,
        ban_member(bot, group_event.group_id, target_id, duration),
        f"已禁言 {target_id}，时长 {duration} 秒",
        "禁言失败，请检查 Bot 权限或目标状态",
    )


@unban.handle()
async def handle_unban(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
):
    group_event = await _group_event_or_finish(unban, event)
    is_superuser = await _require_operator(unban, bot, group_event)
    try:
        target_id = extract_target(args)
    except ValueError as error:
        await unban.finish(str(error))
        return
    await _validate_member_action(unban, bot, group_event, target_id, is_superuser)
    await _run_action(
        unban,
        ban_member(bot, group_event.group_id, target_id, 0),
        f"已解除 {target_id} 的禁言",
        "解除禁言失败，请检查 Bot 权限或目标状态",
    )


@kick.handle()
async def handle_kick(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
):
    group_event = await _group_event_or_finish(kick, event)
    is_superuser = await _require_operator(kick, bot, group_event)
    if (
        not config.group_manager_allow_admin_kick
        and not has_owner_permission(str(group_event.sender.role), is_superuser)
    ):
        await kick.finish("当前配置仅允许群主或超级用户踢人")
        return
    try:
        target_id = extract_target(args)
    except ValueError as error:
        await kick.finish(str(error))
        return
    await _validate_member_action(kick, bot, group_event, target_id, is_superuser)
    reject = "--reject" in args.extract_plain_text().split()
    await _run_action(
        kick,
        kick_member(bot, group_event.group_id, target_id, reject),
        f"已将 {target_id} 移出本群",
        "踢出失败，请检查 Bot 权限或目标状态",
    )


@recall.handle()
async def handle_recall(bot: Bot, event: MessageEvent):
    group_event = await _group_event_or_finish(recall, event)
    await _require_operator(recall, bot, group_event)
    try:
        message_id = extract_reply_message_id(group_event)
    except ValueError as error:
        await recall.finish(str(error))
        return
    await _run_action(
        recall,
        delete_group_message(bot, message_id),
        "消息已撤回",
        "撤回失败，消息可能已撤回或 message_id 无效",
    )


async def _handle_whole_ban(
    matcher: Any,
    bot: Bot,
    event: MessageEvent,
    enable: bool,
) -> None:
    group_event = await _group_event_or_finish(matcher, event)
    await _require_operator(matcher, bot, group_event)
    try:
        bot_member = await _member_info(bot, group_event.group_id, int(bot.self_id))
    except Exception as error:
        logger.warning(f"群管理 Bot 权限查询失败: {error!r}")
        await matcher.finish("无法取得 Bot 群权限，请稍后重试")
        return
    if ROLE_RANK.get(member_role(bot_member), 0) < ROLE_RANK["admin"]:
        await matcher.finish("Bot 不是群管理员，无法执行此操作")
        return
    await _run_action(
        matcher,
        set_whole_ban(bot, group_event.group_id, enable),
        "已开启全员禁言" if enable else "已解除全员禁言",
        "设置全员禁言失败，请检查 Bot 权限",
    )


@whole_ban.handle()
async def handle_whole_ban(bot: Bot, event: MessageEvent):
    await _handle_whole_ban(whole_ban, bot, event, True)


@whole_unban.handle()
async def handle_whole_unban(bot: Bot, event: MessageEvent):
    await _handle_whole_ban(whole_unban, bot, event, False)


async def _handle_admin(
    matcher: Any,
    bot: Bot,
    event: MessageEvent,
    args: Message,
    enable: bool,
) -> None:
    group_event = await _group_event_or_finish(matcher, event)
    await _require_operator(matcher, bot, group_event, owner_only=True)
    try:
        target_id = extract_target(args)
        bot_member = await _member_info(bot, group_event.group_id, int(bot.self_id))
        target_member = await _member_info(bot, group_event.group_id, target_id)
    except ValueError as error:
        await matcher.finish(str(error))
        return
    except Exception as error:
        logger.warning(f"群管理员设置前置查询失败: {error!r}")
        await matcher.finish("无法取得群成员权限信息，请稍后重试")
        return
    if target_id == int(bot.self_id):
        await matcher.finish("不能设置 Bot 自己的管理员身份")
        return
    if member_role(bot_member) != "owner":
        await matcher.finish("仅群主身份的 Bot 可以设置或取消管理员")
        return
    target_role = member_role(target_member)
    if target_role == "owner":
        await matcher.finish("不能修改群主身份")
        return
    if enable and target_role != "member":
        await matcher.finish("目标成员已经是管理员")
        return
    if not enable and target_role != "admin":
        await matcher.finish("目标成员不是管理员")
        return
    await _run_action(
        matcher,
        set_group_admin(bot, group_event.group_id, target_id, enable),
        f"已{'设置' if enable else '取消'} {target_id} 的管理员身份",
        "管理员设置失败，请检查 Bot 权限或目标状态",
    )


@grant_admin.handle()
async def handle_grant_admin(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
):
    await _handle_admin(grant_admin, bot, event, args, True)


@revoke_admin.handle()
async def handle_revoke_admin(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
):
    await _handle_admin(revoke_admin, bot, event, args, False)


join_notice = on_type(GroupIncreaseNoticeEvent, priority=20, block=False)
leave_notice = on_type(GroupDecreaseNoticeEvent, priority=20, block=False)


async def _notice_nickname(bot: Bot, group_id: int, user_id: int) -> str:
    try:
        return member_nickname(await _member_info(bot, group_id, user_id))
    except Exception as error:
        logger.debug(f"群通知昵称查询失败，使用 QQ 号代替: {error!r}")
        return str(user_id)


@join_notice.handle()
async def handle_join_notice(bot: Bot, event: GroupIncreaseNoticeEvent):
    if (
        not config.group_manager_join_notice_enabled
        or event.user_id == int(bot.self_id)
    ):
        return
    nickname = await _notice_nickname(bot, event.group_id, event.user_id)
    message = format_notice(
        config.group_manager_join_message,
        user_id=event.user_id,
        group_id=event.group_id,
        nickname=nickname,
    )
    try:
        await bot.send_group_msg(group_id=event.group_id, message=message)
    except Exception as error:
        logger.warning(f"入群欢迎发送失败: {error!r}")


@leave_notice.handle()
async def handle_leave_notice(bot: Bot, event: GroupDecreaseNoticeEvent):
    if (
        not config.group_manager_leave_notice_enabled
        or event.user_id == int(bot.self_id)
    ):
        return
    nickname = await _notice_nickname(bot, event.group_id, event.user_id)
    message = format_notice(
        config.group_manager_leave_message,
        user_id=event.user_id,
        group_id=event.group_id,
        nickname=nickname,
    )
    try:
        await bot.send_group_msg(group_id=event.group_id, message=message)
    except Exception as error:
        logger.warning(f"退群通知发送失败: {error!r}")


# Bot ADMIN is deliberately separate from the QQ administrator commands above.
bot_admin = on_command("botadmin", permission=SUPERUSER, priority=10, block=True)


def _format_bot_admin_status(group_id: int) -> str:
    overrides = bot_admin_overrides.group_overrides(group_id)
    auto_roles = ", ".join(config.group_manager_admin_auto_roles) or "关闭"
    grants = ", ".join(overrides["grant"]) or "无"
    denies = ", ".join(overrides["deny"]) or "无"
    return (
        f"本群 Bot ADMIN 状态\n"
        f"自动继承 QQ 身份：{auto_roles}\n"
        f"强制授予：{grants}\n"
        f"强制取消：{denies}"
    )


@bot_admin.handle()
async def handle_bot_admin(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
):
    group_event = await _group_event_or_finish(bot_admin, event)
    parts = args.extract_plain_text().split()
    action = parts[0].lower() if parts else ""
    if action == "list" and len(parts) == 1:
        await bot_admin.finish(_format_bot_admin_status(group_event.group_id))
        return
    if action not in {"add", "remove", "reset"}:
        await bot_admin.finish("用法：/botadmin add|remove|reset @用户；/botadmin list")
        return
    try:
        target_id = extract_target(args)
        if action == "add":
            bot_admin_overrides.set_override(group_event.group_id, target_id, True)
            reply = f"已强制授予 {target_id} 本群 Bot ADMIN"
        elif action == "remove":
            bot_admin_overrides.set_override(group_event.group_id, target_id, False)
            reply = f"已强制取消 {target_id} 本群 Bot ADMIN"
        else:
            bot_admin_overrides.reset_override(group_event.group_id, target_id)
            reply = f"已重置 {target_id} 的 Bot ADMIN 覆盖，恢复自动继承"
    except ValueError as error:
        reply = str(error)
    except OSError as error:
        logger.error(f"Bot ADMIN 覆盖规则保存失败: {error}")
        reply = "Bot ADMIN 规则保存失败，原规则保持不变，请检查文件权限"
    await bot_admin.finish(reply)
