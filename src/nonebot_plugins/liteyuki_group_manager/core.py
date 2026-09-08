import re
from collections.abc import Mapping
from typing import Any

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message


ROLE_RANK = {"member": 0, "admin": 1, "owner": 2}
_DURATION_PATTERN = re.compile(r"^(\d+)([smhd]?)$", re.IGNORECASE)
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class SafeTemplateValues(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def parse_duration(value: str, default_seconds: int, max_seconds: int) -> int:
    value = value.strip()
    if not value:
        return min(default_seconds, max_seconds)
    match = _DURATION_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("时间格式错误，请使用 30s、10m、2h 或 1d")
    amount = int(match.group(1))
    unit = match.group(2).lower() or "m"
    seconds = amount * _DURATION_UNITS[unit]
    if seconds <= 0:
        raise ValueError("禁言时间必须大于 0")
    if seconds > max_seconds:
        raise ValueError(f"禁言时间不能超过 {max_seconds} 秒")
    return seconds


def extract_target(message: Message) -> int:
    targets = [
        str(segment.data.get("qq", ""))
        for segment in message
        if segment.type == "at" and str(segment.data.get("qq", "")) != "all"
    ]
    if not targets:
        raise ValueError("请 @ 一名目标成员")
    if len(targets) > 1:
        raise ValueError("一次只能操作一名成员")
    try:
        return int(targets[0])
    except ValueError as error:
        raise ValueError("无法识别目标成员") from error


def extract_reply_message_id(event: Any) -> int:
    reply = getattr(event, "reply", None)
    message_id = getattr(reply, "message_id", None)
    if message_id is None:
        raise ValueError("请回复需要撤回的消息后使用“撤回”")
    return int(message_id)


def group_only_error(event: Any) -> str | None:
    if not isinstance(event, GroupMessageEvent):
        return "该命令只能在群聊中使用"
    return None


def has_management_permission(role: str, is_superuser: bool) -> bool:
    return is_superuser or ROLE_RANK.get(role, 0) >= ROLE_RANK["admin"]


def has_owner_permission(role: str, is_superuser: bool) -> bool:
    return is_superuser or role == "owner"


def validate_target(
    *,
    actor_role: str,
    bot_role: str,
    target_role: str,
    is_superuser: bool,
    bot_id: int,
    target_id: int,
) -> str | None:
    if target_id == bot_id:
        return "不能对 Bot 自己执行此操作"
    if ROLE_RANK.get(bot_role, 0) < ROLE_RANK["admin"]:
        return "Bot 不是群管理员，无法执行此操作"
    if target_role == "owner":
        return "不能操作群主"
    if ROLE_RANK.get(target_role, 0) >= ROLE_RANK.get(bot_role, 0):
        return "目标成员权限不低于 Bot，无法操作"
    if not is_superuser and ROLE_RANK.get(target_role, 0) >= ROLE_RANK.get(actor_role, 0):
        return "不能操作权限不低于自己的成员"
    return None


def format_notice(template: str, *, user_id: int, group_id: int, nickname: str = "") -> str:
    values = SafeTemplateValues(
        user_id=str(user_id),
        group_id=str(group_id),
        nickname=nickname or str(user_id),
    )
    try:
        return template.format_map(values)
    except (ValueError, AttributeError):
        return template


def member_role(member: Mapping[str, Any]) -> str:
    return str(member.get("role", "member"))


def member_nickname(member: Mapping[str, Any]) -> str:
    return str(member.get("card") or member.get("nickname") or "")


async def ban_member(bot: Bot, group_id: int, user_id: int, duration: int) -> None:
    await bot.set_group_ban(group_id=group_id, user_id=user_id, duration=duration)


async def kick_member(bot: Bot, group_id: int, user_id: int, reject: bool) -> None:
    await bot.set_group_kick(
        group_id=group_id,
        user_id=user_id,
        reject_add_request=reject,
    )


async def delete_group_message(bot: Bot, message_id: int) -> None:
    await bot.delete_msg(message_id=message_id)


async def set_whole_ban(bot: Bot, group_id: int, enable: bool) -> None:
    await bot.set_group_whole_ban(group_id=group_id, enable=enable)


async def set_group_admin(bot: Bot, group_id: int, user_id: int, enable: bool) -> None:
    await bot.set_group_admin(group_id=group_id, user_id=user_id, enable=enable)
