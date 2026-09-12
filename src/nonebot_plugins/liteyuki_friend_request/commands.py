"""OneBot V11 event and private SUPERUSER command handlers."""

from __future__ import annotations

from typing import Any

from arclet.alconna import Alconna, Args, Arparma, MultiVar
from nonebot import on_type
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, FriendRequestEvent
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import on_alconna

from .model import FriendRequest
from .service import default_service


friend_request_event = on_type(FriendRequestEvent, priority=20, block=False)
request_list = on_alconna(
    Alconna("好友申请"), aliases={"好友申请列表"}, permission=SUPERUSER, priority=20, block=True
)
approve_request = on_alconna(
    Alconna("好友同意", Args["raw", MultiVar(str), []]),
    permission=SUPERUSER, priority=20, block=True,
)
reject_request = on_alconna(
    Alconna("好友拒绝", Args["request_id", int]),
    permission=SUPERUSER, priority=20, block=True,
)


def _is_group(event: Any) -> bool:
    return getattr(event, "group_id", None) is not None


async def _private_or_finish(event: Event, matcher: Matcher) -> bool:
    if _is_group(event):
        await matcher.finish("请私聊 Bot 处理好友申请。")
        return False
    return True


def pending_text(requests: list[FriendRequest]) -> str:
    if not requests:
        return "当前没有待处理的好友申请。"
    lines = ["待处理好友申请：", ""]
    lines.extend(f"#{item.request_id} | QQ {item.user_id} | {item.comment}" for item in requests)
    lines.extend(["", "使用：", "/好友同意 <编号> [备注]", "/好友拒绝 <编号>"])
    return "\n".join(lines)


def _review_reply(result: Any, approved: bool, remark: str = "") -> str:
    if result.kind == "missing":
        return "未找到待处理好友申请。"
    if result.kind == "handled":
        return "该好友申请已经处理。"
    if result.kind == "offline":
        return "对应 Bot 当前未连接，好友申请仍保留为待处理状态，请稍后重试。"
    if result.kind == "failed":
        return "处理好友申请失败，申请仍保留为待处理状态，请稍后重试。"
    request = result.request
    action = "同意" if approved else "拒绝"
    suffix = f"，备注：{remark}" if approved and remark else ""
    return f"已{action}好友申请 #{request.request_id}（QQ：{request.user_id}）{suffix}"


@friend_request_event.handle()
async def handle_friend_request(bot: Bot, event: FriendRequestEvent) -> None:
    await default_service.receive(bot, event)


@request_list.handle()
async def handle_request_list(event: Event, matcher: Matcher) -> None:
    if not await _private_or_finish(event, matcher):
        return
    await matcher.finish(pending_text(default_service.store.pending()))


@approve_request.handle()
async def handle_approve_request(result: Arparma, event: Event, matcher: Matcher) -> None:
    if not await _private_or_finish(event, matcher):
        return
    raw = [str(value).strip() for value in result.main_args.get("raw", []) if str(value).strip()]
    if not raw or not raw[0].isdigit():
        await matcher.finish("用法：/好友同意 <编号> [备注]")
        return
    request_id = int(raw[0])
    remark = " ".join(raw[1:])
    outcome = await default_service.review(request_id, True, str(getattr(event, "user_id", "")), remark)
    await matcher.finish(_review_reply(outcome, True, remark))


@reject_request.handle()
async def handle_reject_request(result: Arparma, event: Event, matcher: Matcher) -> None:
    if not await _private_or_finish(event, matcher):
        return
    request_id = result.main_args.get("request_id")
    if not isinstance(request_id, int) or request_id <= 0:
        await matcher.finish("用法：/好友拒绝 <编号>")
        return
    outcome = await default_service.review(request_id, False, str(getattr(event, "user_id", "")))
    await matcher.finish(_review_reply(outcome, False))
