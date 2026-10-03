"""Group feature settings and read-only checks of the core permission boundary."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from .config import TwitterConfig

PLUGIN_NAME = "liteyuki_twitter"
DEFAULTS = {"enabled": True, "commands": True, "push": True, "links": True,
            "translate_push": False, "translate_links": False}


def group_model(group_id: str):
    from src.utils.base.data_manager import Group, group_db
    return group_db, group_db.where_one(Group(), "group_id = ?", str(group_id)) or Group(group_id=str(group_id))


def settings(config: TwitterConfig, group_id: str | None) -> dict:
    values = {**DEFAULTS, "provider": config.twitter_translation_provider}
    if group_id is not None:
        _, group = group_model(str(group_id))
        override = group.config.get(PLUGIN_NAME, {})
        if isinstance(override, dict):
            values.update({key: deepcopy(value) for key, value in override.items() if key in values})
    return values


def update(config: TwitterConfig, group_id: str, **changes):
    db, group = group_model(str(group_id))
    existing = group.config.get(PLUGIN_NAME, {})
    current = dict(existing) if isinstance(existing, dict) else {}
    current.update({key: value for key, value in changes.items() if key in DEFAULTS or key == "provider"})
    config_copy = dict(group.config)
    config_copy[PLUGIN_NAME] = current
    group.config = config_copy
    db.save(group)
    return settings(config, str(group_id))


def group_allowed(config: TwitterConfig, group_id: str) -> bool:
    listed = str(group_id) in config.twitter_group_ids
    return listed if config.twitter_group_mode == "whitelist" else not listed


def locally_allowed(config: TwitterConfig, group_id: str | None, channel: str) -> bool:
    if not config.twitter_enabled:
        return False
    if group_id is not None and not group_allowed(config, group_id):
        return False
    values = settings(config, group_id)
    return bool(values["enabled"] and values[channel])


async def core_allowed(group_id: str | None, *, user_id: str | None = None) -> bool:
    from nonebot import require
    require("src.nonebot_plugins.liteyuki_pacman")
    require("src.nonebot_plugins.liteyuki_access_control")
    from src.nonebot_plugins.liteyuki_pacman.common import (
        get_group_enable, get_plugin_global_enable, get_plugin_session_enable,
    )
    from src.nonebot_plugins.liteyuki_access_control.api import is_allowed

    if not get_plugin_global_enable(PLUGIN_NAME):
        return False
    if group_id is not None:
        if not get_group_enable(str(group_id)):
            return False
        session = SimpleNamespace(message_type="group", group_id=str(group_id))
    else:
        session = SimpleNamespace(message_type="private", user_id=str(user_id or ""))
    if not get_plugin_session_enable(session, PLUGIN_NAME):
        return False
    return await is_allowed(PLUGIN_NAME, user_id=user_id, group_id=group_id)


async def allowed(config, group_id, channel, *, user_id=None):
    return locally_allowed(config, group_id, channel) and await core_allowed(group_id, user_id=user_id)
