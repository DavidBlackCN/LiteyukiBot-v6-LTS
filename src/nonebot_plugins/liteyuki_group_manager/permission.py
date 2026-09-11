"""Public Bot ADMIN API. It never grants QQ group-management capabilities."""

from pathlib import Path
from typing import Any

from nonebot.adapters import Bot, Event
from nonebot.permission import Permission, SUPERUSER

from .admin_store import BotAdminOverrideStore
from .config import group_manager_config

BOT_ROLE_SUPERUSER = "superuser"
BOT_ROLE_ADMIN = "admin"
BOT_ROLE_USER = "user"

bot_admin_overrides = BotAdminOverrideStore(Path(group_manager_config.group_manager_admin_data_path) / "admins.json")
bot_admin_overrides.load()


async def is_superuser(bot: Any, event: Any) -> bool:
    """Return whether the sender is a NoneBot SUPERUSER."""
    return await SUPERUSER(bot, event)


def qq_group_role(event: Any) -> str:
    sender = getattr(event, "sender", None)
    role = getattr(sender, "role", None)
    if role is None and isinstance(sender, dict):
        role = sender.get("role")
    return str(role or "member")


async def get_bot_role_for_user(bot: Any, *, group_id: int | str, user_id: int | str,
                                qq_role: str = "member", superuser: bool = False) -> str:
    """Resolve a group Bot role without saving a QQ role."""
    if superuser:
        return BOT_ROLE_SUPERUSER
    override = bot_admin_overrides.get_override(group_id, user_id)
    if override is False:
        return BOT_ROLE_USER
    if override is True:
        return BOT_ROLE_ADMIN
    if qq_role in group_manager_config.group_manager_admin_auto_roles:
        return BOT_ROLE_ADMIN
    return BOT_ROLE_USER


async def get_bot_role(bot: Any, event: Any) -> str:
    """Return superuser, admin, or user for the event sender."""
    if await is_superuser(bot, event):
        return BOT_ROLE_SUPERUSER
    group_id, user_id = getattr(event, "group_id", None), getattr(event, "user_id", None)
    if group_id is None or user_id is None:
        return BOT_ROLE_USER
    return await get_bot_role_for_user(bot, group_id=group_id, user_id=user_id, qq_role=qq_group_role(event))


async def is_admin(bot: Any, event: Any) -> bool:
    """Return whether the sender is SUPERUSER or the current group's Bot ADMIN."""
    return (await get_bot_role(bot, event)) in {BOT_ROLE_SUPERUSER, BOT_ROLE_ADMIN}


async def _admin_permission(bot: Bot, event: Event) -> bool:
    return await is_admin(bot, event)


# Includes SUPERUSER by design; consumers need only use permission=ADMIN.
ADMIN = Permission(_admin_permission)
