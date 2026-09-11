"""SUPERUSER-only credential management commands."""

from __future__ import annotations

from arclet.alconna import Alconna
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import on_alconna

from .errors import BilibiliError
from .runtime import get_client, get_credentials


login_status = on_alconna(
    Alconna("B站登录状态"),
    aliases={"bili login status"},
    permission=SUPERUSER,
    priority=20,
    block=True,
)
logout = on_alconna(
    Alconna("B站登出"),
    aliases={"bili logout"},
    permission=SUPERUSER,
    priority=20,
    block=True,
)


async def login_status_text(client, credentials) -> str:
    credential = credentials.get()
    await client.start()
    nav = await client.get_nav()
    if nav.is_login:
        uid = nav.mid or "未知"
        return f"Bilibili 登录状态有效：uid={uid}，凭据来源={credential.source}。"
    if credential.is_anonymous:
        return "Bilibili 当前为匿名状态。"
    return f"Bilibili 凭据来源={credential.source}，但当前未登录或已失效。"


@login_status.handle()
async def handle_login_status(bot: Bot, event: Event, matcher: Matcher) -> None:
    try:
        text = await login_status_text(get_client(), get_credentials())
    except BilibiliError as exc:
        await matcher.finish(exc.user_message)
        return
    except RuntimeError:
        await matcher.finish("Bilibili 服务当前未启用。")
        return
    await matcher.finish(text)


@logout.handle()
async def handle_logout(bot: Bot, event: Event, matcher: Matcher) -> None:
    try:
        credentials = get_credentials()
    except RuntimeError:
        await matcher.finish("Bilibili 服务当前未启用。")
        return
    source = credentials.get().source
    credentials.logout()
    if source == "config":
        await matcher.finish("已清除扫码登录凭据；当前仍会优先使用 config.yml 中的 bilibili_cookie。")
        return
    await matcher.finish("已清除本地保存的 Bilibili 扫码登录凭据。")
