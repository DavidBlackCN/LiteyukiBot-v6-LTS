import time

import aiohttp
import zhDateTime
from nonebot import logger, require

from src.utils import event as event_utils
from src.utils.base.language import get_user_lang
from src.utils.base.ly_typing import T_Bot, T_MessageEvent

from .api import *

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


status_card_cache = {}  # lang -> bytes


@status_alc.handle()
async def _(
    result: Arparma,
    event: T_MessageEvent,
    bot: T_Bot,
    # refresh: Query[bool] = AlconnaQuery("refresh.value", False),
):
    ulang = get_user_lang(event_utils.get_user_id(event))  # type: ignore
    global status_card_cache
    if (
        result.options["refresh"].value
        or ulang.lang_code not in status_card_cache.keys()
        or (
            ulang.lang_code in status_card_cache.keys()
            and time.time() - status_card_cache[ulang.lang_code][1] > 300  # 缓存
        )
    ):
        motto = dict(zip(("text", "source"), await get_hitokoto()))
        status_card_cache[ulang.lang_code] = (
            (
                await generate_status_card_markdown(
                    bot=await get_bots_data(),
                    hardware=await get_hardware_data(ulang.lang_code),
                    liteyuki=await get_liteyuki_data(),
                    lang=ulang.lang_code,
                    motto=motto,
                )
                if result.options["markdown"].value
                else (
                    await generate_status_card(
                        bot=await get_bots_data(),
                        hardware=await get_hardware_data(ulang.lang_code),
                        liteyuki=await get_liteyuki_data(),
                        lang=ulang.lang_code,
                        motto=motto,
                        bot_id=bot.self_id,
                    )
                )
            ),
            time.time(),
        )
    image = status_card_cache[ulang.lang_code][0]
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
