import asyncio
import time
from collections import defaultdict

import aiohttp
import zhDateTime
from nonebot import logger, require

from src.utils import event as event_utils
from src.utils.base.language import get_user_lang
from src.utils.base.ly_typing import T_Bot, T_MessageEvent

from .api import *
from src.utils.message.html_tool import RenderQueueTimeoutError

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import (
    on_alconna,
    Alconna,
    Subcommand,
    UniMessage,
    Option,
    store_true,
    # AlconnaQuery,
    # Query,
    Arparma,
    Args,
)

HITOKOTO_API_URL = "https://v1.hitokoto.cn/"
HITOKOTO_FALLBACK = ("今天也要保持好心情。", "LiteyukiBot v6 LTS")


async def get_hitokoto() -> tuple[str, str]:
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        headers = {"Accept": "application/json"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as client:
            async with client.get(HITOKOTO_API_URL) as resp:
                resp.raise_for_status()
                payload = await resp.json(content_type=None)

        text = payload.get("hitokoto") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ValueError("一言响应缺少有效 hitokoto 字段")

        author = payload.get("from_who")
        origin = payload.get("from")
        if author and origin:
            source = f"{author}《{origin}》"
        else:
            source = str(author or origin or "一言")
        return text.strip(), source
    except (TimeoutError, aiohttp.ClientError, TypeError, ValueError) as err:
        logger.debug(f"一言 API 不可用，状态卡使用固定文案：{err}")
        return HITOKOTO_FALLBACK


status_alc = on_alconna(
    aliases={"状态"},
    command=Alconna(
        "status",
        Option(
            "-r|--refresh",
            default=False,
            alias={"refr", "r", "刷新"},
            action=store_true,
        ),
        Option(
            "-t|-md|--markdown",
            default=False,
            # alias={"refr", "r", "刷新"},
            action=store_true,
        ),
        Subcommand(
            "memory",
            alias={"mem", "m", "内存"},
        ),
        Subcommand(
            "process",
            alias={"proc", "p", "进程"},
        ),
        # Subcommand(
        #     "refresh",
        #     alias={"refr", "r", "刷新"},
        # ),
    ),
)


STATUS_CACHE_TTL = 300
status_card_cache: dict[tuple[str, bool], tuple[bytes, float]] = {}
_status_render_locks: defaultdict[tuple[str, bool], asyncio.Lock] = defaultdict(asyncio.Lock)


def _cache_is_fresh(cache_key: tuple[str, bool], now: float) -> bool:
    cached = status_card_cache.get(cache_key)
    return cached is not None and now - cached[1] <= STATUS_CACHE_TTL


async def _get_status_card(
    lang_code: str, *, refresh: bool, markdown: bool, bot_id: str
) -> bytes:
    cache_key = (lang_code, markdown)
    request_started_at = time.monotonic()
    if not refresh and _cache_is_fresh(cache_key, request_started_at):
        return status_card_cache[cache_key][0]

    async with _status_render_locks[cache_key]:
        now = time.monotonic()
        cached = status_card_cache.get(cache_key)
        if cached and (
            (not refresh and now - cached[1] <= STATUS_CACHE_TTL)
            or (refresh and cached[1] >= request_started_at)
        ):
            return cached[0]
        try:
            motto = dict(zip(("text", "source"), await get_hitokoto()))
            image = (
                await generate_status_card_markdown(
                    bot=await get_bots_data(),
                    hardware=await get_hardware_data(lang_code),
                    liteyuki=await get_liteyuki_data(),
                    lang=lang_code,
                    motto=motto,
                )
                if markdown
                else await generate_status_card(
                    bot=await get_bots_data(),
                    hardware=await get_hardware_data(lang_code),
                    liteyuki=await get_liteyuki_data(),
                    lang=lang_code,
                    motto=motto,
                    bot_id=bot_id,
                )
            )
        except Exception:
            if cached:
                logger.warning("状态卡刷新失败，继续使用上一张缓存")
                return cached[0]
            raise
        status_card_cache[cache_key] = (image, time.monotonic())
        return image


@status_alc.handle()
async def _(
    result: Arparma,
    event: T_MessageEvent,
    bot: T_Bot,
):
    ulang = get_user_lang(event_utils.get_user_id(event))  # type: ignore
    try:
        image = await _get_status_card(
            ulang.lang_code,
            refresh=result.options["refresh"].value,
            markdown=result.options["markdown"].value,
            bot_id=bot.self_id,
        )
    except RenderQueueTimeoutError:
        await status_alc.finish(UniMessage.text("当前图片渲染任务较多，请稍后再试。"))
        return
    await status_alc.finish(UniMessage.image(raw=image))

@status_alc.assign("memory")
async def _():
    pass


@status_alc.assign("process")
async def _():
    pass


time_query = on_alconna(
    command=Alconna(
        "时间",
    ),
    aliases={"时间查询", "timeq", "timequery"},
)


@time_query.handle()
async def _(
    event: T_MessageEvent,
    bot: T_Bot,
):
    # ulang = get_user_lang(event_utils.get_user_id(event))  # type: ignore
    await time_query.finish(
        UniMessage.text(zhDateTime.DateTime.now().chinesize.chinese_text)
    )


number_read = on_alconna(
    command=Alconna(
        "读数",
        Option("-g|--group", default=False, action=store_true),
        Args["number", str],
    ),
    aliases={"readout_number", "number_read"},
)


@number_read.handle()
async def _(
    event: T_MessageEvent,
    bot: T_Bot,
    result: Arparma,
):
    num = result.main_args.get("number", "")
    try:
        num = int(num)
    except:
        await number_read.finish(UniMessage.text("小数点后直接读，不是数字没法读"))

    if num < 0:
        result_readout = "负"
        num = abs(num)
    else:
        result_readout = ""

    try:
        if result.options["group"].value:
            result_readout += zhDateTime.int_2_grouped_han_str(num)
        else:
            result_readout += zhDateTime.int_hanzify(num)
    except IndexError as e:
        await number_read.finish(UniMessage.text("数字太大了：{}".format(e)))

    await number_read.finish(UniMessage.text(result_readout))
