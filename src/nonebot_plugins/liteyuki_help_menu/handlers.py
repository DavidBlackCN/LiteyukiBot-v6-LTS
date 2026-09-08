import asyncio
import hashlib
import json
import re
import sys
from collections import OrderedDict
from time import monotonic

from nonebot import get_driver, get_loaded_plugins, get_plugin, logger, on_message, require
from nonebot.adapters import Bot, Event
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State

from . import config
from .catalog import collect_plugins, page_context

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import UniMessage
from src.utils.base.resource import get_path
from src.utils.message.html_tool import template2image_element


def parse_request(raw, prefixes):
    raw = raw.strip()
    for prefix in sorted((p for p in prefixes if p), key=len, reverse=True):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    match = re.fullmatch(r"(?:帮助|菜单|help)(?:\s+(.*))?", raw, re.I | re.S)
    return match.group(1) or "" if match else None


async def menu_rule(event: Event, state: T_State):
    if event.get_type() != "message":
        return False
    query = parse_request(event.get_plaintext(), get_driver().config.command_start)
    if query is None:
        return False
    state["help_menu_query"] = query
    return True


# Pacman's legacy help is priority 1; leave it available when this is disabled.
menu = on_message(rule=menu_rule, priority=0, block=True)
_cache = OrderedDict()
_render_lock = asyncio.Lock()


async def visible_catalog(bot, event):
    items = collect_plugins(get_loaded_plugins(), config)
    pacman = get_plugin("liteyuki_pacman")
    common = sys.modules.get(f"{pacman.module_name}.common") if pacman else None
    access = get_plugin("liteyuki_access_control")
    api = sys.modules.get(f"{access.module_name}.api") if access else None
    superuser = await SUPERUSER(bot, event)
    try:
        user = event.get_user_id()
    except (ValueError, NotImplementedError):
        user = None
    group = getattr(event, "group_id", None)
    if group is None:
        group = getattr(getattr(event, "guild", None), "id", None)
    visible = []
    for item in items:
        if common:
            try:
                enabled = common.get_plugin_global_enable(item["id"]) and common.get_plugin_session_enable(event, item["id"])
                item["status"] = "会话已启用（仍受业务权限限制）" if enabled else "当前会话已停用"
            except (AttributeError, TypeError, ValueError):
                pass
        if config.help_menu_filter_access and api:
            if not await api.is_allowed(item["id"], user, str(group) if group is not None else None,
                                        is_superuser=superuser):
                continue
        visible.append(item)
    return visible


async def render_menu(data):
    template = get_path("templates/help_menu.html")
    # Context includes visible plugin metadata and current status. Never cache by
    # query alone: users may have different access rules. Bound memory and TTL.
    key = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    async with _render_lock:
        now = monotonic()
        for old_key, (created, _) in list(_cache.items()):
            if now - created > 60:
                del _cache[old_key]
        if key in _cache:
            return _cache[key][1]
        image = await template2image_element(
            template, {"data": data}, "body", wait_for="window.helpMenuReady === true",
            wait_timeout=5000,
        )
        if len(image) <= 4 * 1024 * 1024:
            _cache[key] = (now, image)
            while len(_cache) > 8:
                _cache.popitem(last=False)
        return image


@menu.handle()
async def handle_menu(bot: Bot, event: Event, state: T_State):
    try:
        items = await visible_catalog(bot, event)
        data = page_context(items, state["help_menu_query"], config.help_menu_page_size,
                            config.help_menu_enable_pinyin_search)
        image = await render_menu(data)
    except ValueError as error:
        await menu.finish(str(error))
        return
    except Exception as error:
        logger.warning(f"帮助菜单生成失败：{error}")
        await menu.finish("帮助图片暂时无法生成，请稍后重试")
        return
    await UniMessage.image(raw=image).send()
