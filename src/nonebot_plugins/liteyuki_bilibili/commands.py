"""SUPERUSER-only credential management commands."""

from __future__ import annotations

import asyncio

from arclet.alconna import Alconna, Args, MultiVar
from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import UniMessage, on_alconna

from src.utils.base.permission import GROUP_ADMIN, GROUP_OWNER

from .errors import BilibiliError
from .login import make_qr_png, wait_for_qr_login
from .migration import migrate_legacy_data
from .runtime import get_client, get_credentials, get_store


def subscription_options(tokens: list[str], config) -> tuple[bool, bool, bool]:
    flags = {token.lower() for token in tokens if token.startswith("--")}
    known = {"--dynamic", "--video", "--live", "--all"}
    unknown = flags - known
    if unknown:
        raise ValueError(f"不支持的订阅选项：{sorted(unknown)[0]}")
    if not flags:
        return config.bilibili_push_dynamic, config.bilibili_push_video, config.bilibili_push_live
    if "--all" in flags:
        return True, True, True
    return "--dynamic" in flags, "--video" in flags, "--live" in flags


async def initialize_subscription_baseline(client, uid: str) -> tuple[str, str, str]:
    """Unavailable sources remain pending; the scheduler will baseline them later."""
    await client.start()
    dynamics, videos, live = await asyncio.gather(
        client.get_latest_dynamics(uid), client.get_latest_videos(uid), client.get_live_status(uid),
        return_exceptions=True,
    )
    dynamic_id = dynamics[0].event_id if isinstance(dynamics, list) and dynamics else ""
    video_id = ""
    if isinstance(videos, list) and videos:
        video_id = videos[0].bvid or videos[0].aid
    live_state = "unknown" if isinstance(live, Exception) else ("live" if live.live else "offline")
    return dynamic_id, video_id, live_state


login_status = on_alconna(
    Alconna("B站登录状态"),
    aliases={"bili login status"},
    permission=SUPERUSER,
    priority=20,
    block=True,
)
login = on_alconna(
    Alconna("B站登录"),
    aliases={"bili login"},
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
migrate = on_alconna(
    Alconna("B站迁移"),
    aliases={"bili migrate"},
    permission=SUPERUSER,
    priority=20,
    block=True,
)
subscribe = on_alconna(
    Alconna("B站订阅", Args["raw", MultiVar(str)]), aliases={"bili subscribe"},
    permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN, priority=20, block=True,
)
unsubscribe = on_alconna(
    Alconna("B站取消", Args["uid", str]), aliases={"bili unsubscribe"},
    permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN, priority=20, block=True,
)
subscription_list = on_alconna(
    Alconna("B站订阅列表"), aliases={"bili subscriptions"},
    permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN, priority=20, block=True,
)

_qr_login_lock = asyncio.Lock()


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


async def start_qr_login(client, credentials, send_image, send_text) -> None:
    """Send one QR code then wait for Bilibili confirmation without exposing secrets."""
    await client.start()
    session = await client.create_qr_login()
    image = make_qr_png(session.url)
    try:
        await send_image(image)
    except Exception:
        # This fallback is confined to a SUPERUSER private chat by the handler.
        logger.warning("Bilibili 登录二维码图片发送失败，改发一次性登录链接。")
        await send_text(f"二维码图片发送失败，请在 3 分钟内打开以下 Bilibili 登录链接：\n{session.url}")
    await wait_for_qr_login(
        client,
        credentials,
        session.key,
        on_scanned=lambda: send_text("已扫码，请在 Bilibili 客户端确认登录。"),
    )


@login.handle()
async def handle_login(event: Event, matcher: Matcher) -> None:
    if getattr(event, "group_id", None) is not None:
        await matcher.finish("为防止登录凭据泄露，请私聊 Bot 使用 /B站登录。")
        return
    if _qr_login_lock.locked():
        await matcher.finish("已有 Bilibili 扫码登录正在进行，请稍后再试。")
        return
    try:
        async with _qr_login_lock:
            credentials = get_credentials()
            if credentials.get().source == "config":
                await matcher.finish(
                    "当前优先使用 config.yml 中的 bilibili_cookie；请先清空该配置后再使用 /B站登录。"
                )
                return
            await matcher.send("请在 3 分钟内使用 Bilibili 客户端扫码。")
            await start_qr_login(
                get_client(),
                credentials,
                lambda image: matcher.send(UniMessage.image(raw=image)),
                matcher.send,
            )
    except BilibiliError as exc:
        await matcher.finish(exc.user_message)
        return
    except RuntimeError:
        await matcher.finish("Bilibili 服务当前未启用。")
        return
    await matcher.finish("Bilibili 登录成功，扫码凭据已安全保存到本地数据目录。")


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


@migrate.handle()
async def handle_migrate(bot: Bot, event: Event, matcher: Matcher) -> None:
    try:
        report = migrate_legacy_data(get_store(), get_credentials())
    except RuntimeError:
        await matcher.finish("Bilibili 服务当前未启用。")
        return
    if not report.source_found:
        await matcher.finish("未发现可迁移的旧 Bilibili 数据文件。")
        return
    await matcher.finish(
        "Bilibili 旧数据迁移完成："
        f"新增 {report.imported}，更新 {report.updated}，跳过 {report.skipped}，"
        f"待首次轮询建立 baseline {report.baseline_pending}。"
    )


def _target(event: Event) -> tuple[str, str]:
    group_id = getattr(event, "group_id", None)
    return ("group", str(group_id)) if group_id is not None else ("private", str(getattr(event, "user_id", "")))


@subscribe.handle()
async def handle_subscribe(result, event: Event, matcher: Matcher) -> None:
    from . import config

    raw = [str(value) for value in result.main_args.get("raw", [])]
    if not raw or not raw[0].isdigit():
        await matcher.finish("用法：/B站订阅 <UID> [--dynamic|--video|--live|--all]")
        return
    try:
        dynamic, video, live = subscription_options(raw[1:], config)
        if not any((dynamic, video, live)):
            raise ValueError("至少选择一种订阅类型")
        target_type, target_id = _target(event)
        store = get_store()
        item, created = store.add(
            target_type=target_type, target_id=target_id, uid=raw[0],
            dynamic_enabled=dynamic, video_enabled=video, live_enabled=live,
            created_by=str(getattr(event, "user_id", "")),
        )
        if created:
            dynamic_id, video_id, live_state = await initialize_subscription_baseline(get_client(), raw[0])
            item = store.initialize_baseline(
                target_type, target_id, raw[0], dynamic_id=dynamic_id, video_id=video_id, live_state=live_state
            )
    except ValueError as exc:
        await matcher.finish(str(exc))
        return
    except (BilibiliError, RuntimeError):
        await matcher.finish("订阅已保存；首次成功轮询将建立 baseline，不会推送历史内容。")
        return
    kinds = "、".join(label for enabled, label in ((item.dynamic_enabled, "动态"), (item.video_enabled, "视频"), (item.live_enabled, "直播")) if enabled)
    await matcher.finish(f"{'已更新' if not created else '已订阅并建立 baseline'} UP {item.uid}：{kinds}。")


@unsubscribe.handle()
async def handle_unsubscribe(result, event: Event, matcher: Matcher) -> None:
    uid = str(result.main_args.get("uid", ""))
    if not uid.isdigit():
        await matcher.finish("UID 必须为数字。")
        return
    try:
        target_type, target_id = _target(event)
        removed = get_store().remove(target_type, target_id, uid)
    except RuntimeError:
        await matcher.finish("Bilibili 服务当前未启用。")
        return
    await matcher.finish("已取消订阅。" if removed else "当前会话未订阅该 UID。")


@subscription_list.handle()
async def handle_subscription_list(event: Event, matcher: Matcher) -> None:
    try:
        target_type, target_id = _target(event)
        subscriptions = get_store().list_target(target_type, target_id)
    except RuntimeError:
        await matcher.finish("Bilibili 服务当前未启用。")
        return
    if not subscriptions:
        await matcher.finish("当前会话没有 Bilibili 订阅。")
        return
    lines = ["Bilibili 订阅列表："]
    for item in subscriptions:
        kinds = "/".join(label for enabled, label in ((item.dynamic_enabled, "动态"), (item.video_enabled, "视频"), (item.live_enabled, "直播")) if enabled)
        lines.append(f"- UID {item.uid}：{kinds}")
    await matcher.finish("\n".join(lines))
