import asyncio
import math
import random

import nonebot
from nonebot import Bot, get_driver, get_loaded_plugins, on_message, require
from nonebot.consts import CMD_KEY, PREFIX_KEY
from nonebot.internal.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot.typing import T_State

from src.utils import event as event_utils
from src.utils.base.data_manager import Group, group_db
from src.utils.base.ly_typing import T_MessageEvent
from src.utils.base.permission import GROUP_ADMIN, GROUP_OWNER
from src.utils.base.word_bank import get_reply

from .utils import get_keywords

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna

driver = get_driver()
group_reply_probability: dict[str, float] = {}
default_reply_probability = 0.05
cut_probability = 0.4  # 分几句话的概率


def normalize_group_id(group_id: object) -> str:
    """Use the database model's string representation for every cache key."""
    return str(group_id)


def is_valid_probability(probability: object) -> bool:
    if isinstance(probability, bool) or not isinstance(probability, (int, float)):
        return False
    value = float(probability)
    return math.isfinite(value) and 0.0 <= value <= 1.0


def cache_group_probability(group_id: object, probability: object) -> bool:
    key = normalize_group_id(group_id)
    if not is_valid_probability(probability):
        group_reply_probability.pop(key, None)
        return False
    group_reply_probability[key] = float(probability)
    return True


def get_group_probability(group_id: object) -> float:
    return group_reply_probability.get(
        normalize_group_id(group_id), default_reply_probability
    )


def load_group_probabilities() -> None:
    """Rebuild the cache from persisted group configuration."""
    group_reply_probability.clear()
    for group in group_db.where_all(Group(), default=[]):
        probability = group.config.get("reply_probability", default_reply_probability)
        if not cache_group_probability(group.group_id, probability):
            nonebot.logger.warning(
                f"忽略群组 {group.group_id} 中无效的回复概率：{probability}"
            )


def save_group_probability(group_id: object, probability: object) -> float:
    if not is_valid_probability(probability):
        raise ValueError("回复概率必须是 0 到 1 之间的有限数值")

    normalized_group_id = normalize_group_id(group_id)
    value = float(probability)
    group: Group = group_db.where_one(
        Group(),
        "group_id = ?",
        normalized_group_id,
        default=Group(group_id=normalized_group_id),
    )
    group.config = dict(group.config)
    group.config["reply_probability"] = value
    group_db.save(group)
    # Keep the current process in sync even if a test or embedding replaces the DB.
    cache_group_probability(normalized_group_id, value)
    return value


def get_bot_nicknames(bot: Bot) -> set[str]:
    configured = getattr(bot.config, "nickname", set())
    if isinstance(configured, str):
        return {configured} if configured else set()
    return {str(nickname) for nickname in configured if str(nickname)}


def is_registered_command(
    text: str,
    state: T_State,
    plugins: object = None,
) -> bool:
    """Return whether a message matched a loaded NoneBot/Alconna command."""
    prefix_state = state.get(PREFIX_KEY, {})
    if isinstance(prefix_state, dict) and prefix_state.get(CMD_KEY) is not None:
        return True

    stripped = text.lstrip()
    starts = {str(start) for start in get_driver().config.command_start}
    candidates = []
    for start in sorted((start for start in starts if start), key=len, reverse=True):
        if stripped.startswith(start):
            candidates.append(stripped[len(start) :].lstrip())
    if "" in starts:
        candidates.append(stripped)
    candidates = [candidate for candidate in dict.fromkeys(candidates) if candidate]
    if not candidates:
        return False

    loaded_plugins = get_loaded_plugins() if plugins is None else plugins
    for plugin in loaded_plugins:
        for command_matcher in getattr(plugin, "matcher", ()):
            command = getattr(command_matcher, "command", None)
            parse = getattr(command, "parse", None)
            if not callable(parse):
                continue
            for candidate in candidates:
                try:
                    if getattr(parse(candidate), "matched", False):
                        return True
                except Exception:
                    # A third-party parser must not break Smart Reply handling.
                    continue
    return False


@on_alconna(
    command=Alconna(
        "set-reply-probability",
        Args["probability", float, default_reply_probability],
    ),
    aliases={"设置回复概率"},
    permission=SUPERUSER | GROUP_ADMIN | GROUP_OWNER,
).handle()
async def _(result: Arparma, event: T_MessageEvent, matcher: Matcher):
    if event_utils.get_message_type(event) != "group":
        return

    group_id = event_utils.get_group_id(event)
    probability = result.main_args.get("probability")
    if group_id is None or not is_valid_probability(probability):
        await matcher.send("回复概率必须是 0 到 1 之间的有限数值")
        return

    value = save_group_probability(group_id, probability)
    await matcher.send(
        f"已将群组{normalize_group_id(group_id)}的回复概率设置为{value:g}"
    )


@group_db.on_save
def _(model: Group):
    probability = model.config.get("reply_probability", default_reply_probability)
    cache_group_probability(model.group_id, probability)


@driver.on_bot_connect
async def _(bot: Bot):
    # Rebuilding is idempotent for multiple bots and reconnects.
    load_group_probabilities()


@on_message(priority=100).handle()
async def _(event: T_MessageEvent, bot: Bot, state: T_State, matcher: Matcher):
    message = event.get_message()
    plain_text = message.extract_plain_text() if message is not None else ""
    if not plain_text or not plain_text.strip():
        return
    if is_registered_command(plain_text, state):
        return

    kws = await get_keywords(plain_text)
    if not kws:
        return

    tome = await to_me()(event=event, bot=bot, state=state)
    if not tome:
        nicknames = get_bot_nicknames(bot)
        tome = any(keyword in nicknames for keyword in kws)

    message_type = event_utils.get_message_type(event)
    if tome or message_type == "private":
        probability = 1.0
    elif message_type == "group":
        group_id = event_utils.get_group_id(event)
        probability = get_group_probability(group_id)
    else:
        probability = default_reply_probability

    if random.random() >= probability:
        return

    reply = get_reply(kws)
    if not isinstance(reply, str) or not reply.strip():
        return

    if random.random() < cut_probability:
        split_reply = (
            reply.replace("。", "||")
            .replace("，", "||")
            .replace("！", "||")
            .replace("？", "||")
        )
        replies = [part.strip() for part in split_reply.split("||") if part.strip()]
        for part in replies:
            await asyncio.sleep(random.random() * 2)
            await matcher.send(part)
    else:
        await asyncio.sleep(random.random() * 3)
        await matcher.send(reply)
