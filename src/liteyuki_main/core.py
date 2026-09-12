import time
from typing import AnyStr

import time
from typing import AnyStr

import nonebot
import pip
from nonebot import get_driver, require
from nonebot.adapters import onebot
from nonebot.adapters.onebot.v11 import Message, unescape
from nonebot.internal.matcher import Matcher
from nonebot.permission import SUPERUSER

# from src.liteyuki.core import Reloader
from src.utils import event as event_utils, satori_utils
from src.utils.base.config import get_config
from src.utils.satori_utils.compat import is_satori_object
from src.utils.base.data_manager import TempConfig, common_db
from src.utils.base.language import get_user_lang
from src.utils.base.ly_typing import T_Bot, T_MessageEvent
from src.utils.message.message import MarkdownMessage as md, broadcast_to_superusers
from .api import update_liteyuki  # type: ignore
from .reload_state import begin_reload, mark_worker_started, prepare_reload_receipt
from ..utils.base import reload  # type: ignore
from ..utils.base.ly_function import get_function  # type: ignore
from ..utils.message.html_tool import md_to_pic

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
from nonebot_plugin_alconna import (
    UniMessage,
    on_alconna,
    Alconna,
    Args,
    Arparma,
    MultiVar,
)
from nonebot_plugin_apscheduler import scheduler


driver = get_driver()


@on_alconna(
    command=Alconna(
        "liteyuki-echo",
        Args["text", str, ""],
    ),
    permission=SUPERUSER,
).handle()
# Satori OK
async def _(bot: T_Bot, matcher: Matcher, result: Arparma):
    if text := result.main_args.get("text"):
        await matcher.finish(Message(unescape(text)))
    else:
        await matcher.finish(f"你好！Liteyuki v6 LTS 向你问好~\n此机 {bot.self_id}")


@on_alconna(
    command=Alconna(
        "liteecho",
        # Args["text", str, ""],
    ),
    # permission=SUPERUSER
).handle()
# Satori OK
async def _(bot: T_Bot, matcher: Matcher, result: Arparma):
    await matcher.finish(f"Hello! LiteyukiBot v6 LTS!\nBot {bot.self_id}")


@on_alconna(
    aliases={"更新轻雪", "更新Liteyuki"}, command=Alconna("update-liteyuki"), permission=SUPERUSER
).handle()
# Satori OK
async def _(bot: T_Bot, event: T_MessageEvent, matcher: Matcher):
    # 使用git pull更新

    ulang = get_user_lang(
        str(event.user.id if is_satori_object(event) else event.user_id)
    )
    success, logs = update_liteyuki()
    reply = "Liteyuki v6 LTS 更新完成！\n"
    reply += f"```\n{logs}\n```\n"
    btn_restart = md.btn_cmd(ulang.get("liteyuki.restart_now"), "reload-liteyuki")
    # pip.main(["install", "-r", "requirements.txt"])
    reply += f"{ulang.get('liteyuki.update_restart', RESTART=btn_restart)}"
    # await md.send_md(reply, bot)
    img_bytes = await md_to_pic(reply)
    await UniMessage.send(UniMessage.image(raw=img_bytes))


@on_alconna(
    aliases={"重启轻雪", "重载轻雪", "重启Liteyuki"},
    command=Alconna(
        "reload-liteyuki",
    ),
    permission=SUPERUSER,
).handle()
# Satori OK
async def _(matcher: Matcher, bot: T_Bot, event: T_MessageEvent):
    await matcher.send("Liteyuki v6 LTS 正在重载")
    temp_data = common_db.where_one(TempConfig(), default=TempConfig())

    begin_reload(
        temp_data.data,
        bot_id=bot.self_id,
        session_type=event_utils.get_message_type(event),
        session_id=(
            (event.group_id if event.message_type == "group" else event.user_id)
            if not is_satori_object(event)
            else event.chan_active.id
        ),
    )
    common_db.save(temp_data)
    nonebot.logger.info("收到 reload-liteyuki 请求，等待 Bot {} 重连回执", str(bot.self_id))
    reload()



@on_alconna(
    command=Alconna(
        "/function",
        Args["function", str]["args", MultiVar(str), ()],
    ),
    permission=SUPERUSER,
).handle()
async def _(result: Arparma, bot: T_Bot, event: T_MessageEvent, matcher: Matcher):
    """
    调用轻雪函数
    Args:
        result:
        bot:
        event:

    Returns:

    """
    function_name = result.main_args.get("function")
    args: tuple[str] = result.main_args.get("args", ())
    _args = []
    _kwargs = {
        "USER_ID": str(event.user_id),
        "GROUP_ID": str(event.group_id) if event.message_type == "group" else "0",
        "BOT_ID": str(bot.self_id),
    }

    for arg in args:
        arg = arg.replace("\\=", "EQUAL_SIGN")
        if "=" in arg:
            key, value = arg.split("=", 1)
            value = unescape(value.replace("EQUAL_SIGN", "="))
            try:
                value = eval(value)
            except:
                value = value
            _kwargs[key] = value
        else:
            _args.append(arg.replace("EQUAL_SIGN", "="))

    ly_func = get_function(function_name)
    ly_func.bot = bot if "BOT_ID" not in _kwargs else nonebot.get_bot(_kwargs["BOT_ID"])
    ly_func.matcher = matcher

    await ly_func(*tuple(_args), **_kwargs)


@on_alconna(
    command=Alconna(
        "/api",
        Args["api", str]["args", MultiVar(AnyStr), ()],
    ),
    permission=SUPERUSER,
).handle()
async def _(result: Arparma, bot: T_Bot, event: T_MessageEvent, matcher: Matcher):
    """
    调用API
    Args:
        result:
        bot:
        event:

    Returns:

    """
    api_name = result.main_args.get("api")
    args: tuple[str] = result.main_args.get(
        "args", ()
    )  # 类似于url参数，但每个参数间用空格分隔，空格是%20
    args_dict = {}

    for arg in args:
        key, value = arg.split("=", 1)

        args_dict[key] = unescape(value.replace("%20", " "))

    if api_name in need_user_id and "user_id" not in args_dict:
        args_dict["user_id"] = str(event.user_id)
    if (
        api_name in need_group_id
        and "group_id" not in args_dict
        and event.message_type == "group"
    ):
        args_dict["group_id"] = str(event.group_id)

    if "message" in args_dict:
        args_dict["message"] = Message(eval(args_dict["message"]))

    if "messages" in args_dict:
        args_dict["messages"] = Message(eval(args_dict["messages"]))

    try:
        result = await bot.call_api(api_name, **args_dict)
    except Exception as e:
        result = str(e)

    args_show = "\n".join("- %s: %s" % (k, v) for k, v in args_dict.items())
    await matcher.finish(f"API: {api_name}\n\nArgs: \n{args_show}\n\nResult: {result}")


@driver.on_startup
async def on_startup():
    temp_data = common_db.where_one(TempConfig(), default=TempConfig())
    reload_status, elapsed = mark_worker_started(temp_data.data)
    if reload_status == "pending":
        common_db.save(temp_data)
        nonebot.logger.info("Worker 启动检测到 reload 状态，已记录耗时 {:.2f} 秒", elapsed)
    elif reload_status == "expired":
        common_db.save(temp_data)
        nonebot.logger.warning("Worker 启动检测到过期 reload 状态，已清理且不会发送迟到回执")
    """
    该部分将迁移至轻雪生命周期
    Returns:

    """


@driver.on_shutdown
async def on_shutdown():
    pass


@driver.on_bot_connect
async def _(bot: T_Bot):
    temp_data = common_db.where_one(TempConfig(), default=TempConfig())
    if is_satori_object(bot):
        await satori_utils.user_infos.load_friends(bot)
    reload_status, receipt = prepare_reload_receipt(temp_data.data, str(bot.self_id))
    if reload_status == "mismatch":
        nonebot.logger.warning(
            "reload 回执 Bot ID 不匹配：等待 {}，收到 {}",
            str(temp_data.data.get("reload_bot_id", "")),
            str(bot.self_id),
        )
        return
    if reload_status == "expired":
        common_db.save(temp_data)
        nonebot.logger.warning("过期 reload 状态已清理，不发送迟到成功回执")
        return
    if reload_status != "receipt":
        return

    reload_session_type = receipt["session_type"]
    reload_session_id = receipt["session_id"]
    delta_time = receipt["delta_time"]
    reload_time = receipt["reload_time"]
    common_db.save(temp_data)
    nonebot.logger.info("reload 成功回执：Bot {}", str(bot.self_id))
    return_msg = "Liteyuki v6 LTS 核心重载耗时 {:.2f} 秒\n客户端恢复耗时 {:.2f} 秒\n*此数据仅作参考，具体计时请以实际为准".format(
        delta_time, time.time() - reload_time
    )

    if is_satori_object(bot):
        await bot.send_message(
            channel_id=reload_session_id,
            message=return_msg,
        )
    elif isinstance(bot, onebot.v11.Bot):
        await bot.send_msg(
            message_type=reload_session_type,
            user_id=reload_session_id,
            group_id=reload_session_id,
            message=return_msg,
        )
    elif isinstance(bot, onebot.v12.Bot):
        await bot.send_msg(
            message_type=reload_session_type,
            user_id=reload_session_id,
            group_id=reload_session_id,
            message=return_msg,
            detail_type="group",
        )
    else:
        await bot.call_api(
            "send_msg",
            message_type=reload_session_type,
            user_id=reload_session_id,
            group_id=reload_session_id,
            message=return_msg,
        )


# 每天4点更新
@scheduler.scheduled_job("cron", hour=4)
async def every_day_update():
    if get_config("auto_update", default=True):
        result, logs = update_liteyuki()
        pip.main(["install", "-r", "requirements.txt"])
        if result:
            await broadcast_to_superusers(f"Liteyuki v6 LTS 已更新：```\n{logs}\n```")
            nonebot.logger.info(f"Liteyuki v6 LTS 已更新：{logs}")
            reload()
        else:
            nonebot.logger.info(logs)


# 需要用户id的api
need_user_id = (
    "send_private_msg",
    "send_msg",
    "set_group_card",
    "set_group_special_title",
    "get_stranger_info",
    "get_group_member_info",
)

need_group_id = (
    "send_group_msg",
    "send_msg",
    "set_group_card",
    "set_group_name",
    "set_group_special_title",
    "get_group_member_info",
    "get_group_member_list",
    "get_group_honor_info",
)
