"""Storage, notifications and review operations for friend requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import nonebot
from nonebot import logger

from src.utils.base.data import Database

from .model import FriendRequest, FriendRequestSequence


PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _event_time(event: Any) -> str:
    value = getattr(event, "time", None)
    if value is not None:
        try:
            return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OSError, OverflowError):
            logger.warning("好友申请事件时间无效，使用当前时间记录")
    return _now()


class FriendRequestStore:
    """Small LiteModel-backed repository, isolated from other plugin tables."""

    def __init__(self, path: str | Path = "data/liteyuki/friend_request.ldb") -> None:
        self.db = Database(str(path))
        self.db.auto_migrate(FriendRequest(), FriendRequestSequence())

    def find_by_bot_flag(self, bot_id: str, flag: str) -> FriendRequest | None:
        return self.db.where_one(FriendRequest(), "bot_id = ? AND flag = ?", bot_id, flag)

    def create(self, *, bot_id: str, user_id: str, comment: str, flag: str, created_at: str) -> tuple[FriendRequest, bool]:
        existing = self.find_by_bot_flag(bot_id, flag)
        if existing is not None:
            return existing, False
        sequence = self.db.where_one(FriendRequestSequence())
        if sequence is None:
            sequence = FriendRequestSequence(next_request_id=1)
        request = FriendRequest(
            request_id=sequence.next_request_id,
            bot_id=bot_id,
            user_id=user_id,
            comment=comment,
            flag=flag,
            created_at=created_at,
        )
        sequence.next_request_id += 1
        self.db.save(sequence, request)
        return request, True

    def get(self, request_id: int) -> FriendRequest | None:
        return self.db.where_one(FriendRequest(), "request_id = ?", request_id)

    def pending(self) -> list[FriendRequest]:
        records = self.db.where_all(FriendRequest(), "status = ?", PENDING) or []
        return sorted(records, key=lambda item: item.request_id)

    def mark_handled(self, request: FriendRequest, status: str, handled_by: str) -> None:
        request.status = status
        request.handled_at = _now()
        request.handled_by = handled_by
        self.db.save(request)

    def cleanup_history(self, days: int) -> None:
        cutoff = datetime.now() - timedelta(days=days)
        records = self.db.where_all(FriendRequest()) or []
        for record in records:
            if record.status == PENDING or not record.handled_at:
                continue
            try:
                handled_at = datetime.strptime(record.handled_at, "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                logger.warning("好友申请历史时间异常，保留记录 #%s", record.request_id)
                continue
            if handled_at < cutoff:
                self.db.delete(FriendRequest(), "id = ?", record.id)


@dataclass(frozen=True)
class ReviewResult:
    kind: Literal["success", "missing", "handled", "offline", "failed"]
    request: FriendRequest | None = None


class FriendRequestService:
    def __init__(self, store: FriendRequestStore) -> None:
        self.store = store
        self._lock = asyncio.Lock()

    async def receive(self, bot: Any, event: Any) -> FriendRequest | None:
        """Persist a V11 request and notify each configured SUPERUSER once."""
        bot_id = str(getattr(event, "self_id", None) or getattr(bot, "self_id", ""))
        flag = str(getattr(event, "flag", "") or "")
        if not bot_id or not flag:
            logger.warning("好友申请缺少 bot_id 或 flag，未保存")
            return None
        try:
            async with self._lock:
                request, created = self.store.create(
                    bot_id=bot_id,
                    user_id=str(getattr(event, "user_id", "")),
                    comment=str(getattr(event, "comment", "") or ""),
                    flag=flag,
                    created_at=_event_time(event),
                )
        except Exception as error:
            logger.warning("好友申请保存失败: %r", error)
            return None
        if created:
            await self.notify_superusers(bot, request)
        return request

    async def notify_superusers(self, bot: Any, request: FriendRequest) -> None:
        superusers = getattr(getattr(bot, "config", None), "superusers", set()) or set()
        if not superusers:
            logger.warning("收到好友申请 #%s，但未配置 SUPERUSER", request.request_id)
            return
        message = notification_text(request)
        for superuser in superusers:
            try:
                await bot.send_private_msg(user_id=_qq_user_id(superuser), message=message)
            except Exception as error:
                logger.warning("好友申请通知 SUPERUSER %s 失败: %r", superuser, error)

    async def review(self, request_id: int, approve: bool, handled_by: str, remark: str = "") -> ReviewResult:
        """Call the receiving Bot then persist a successful decision under one lock."""
        async with self._lock:
            try:
                request = self.store.get(request_id)
            except Exception as error:
                logger.warning("读取好友申请 #%s 失败: %r", request_id, error)
                return ReviewResult("missing")
            if request is None:
                return ReviewResult("missing")
            if request.status != PENDING:
                return ReviewResult("handled", request)
            try:
                bot = nonebot.get_bot(request.bot_id)
            except Exception:
                return ReviewResult("offline", request)
            try:
                if approve:
                    await bot.set_friend_add_request(flag=request.flag, approve=True, remark=remark)
                else:
                    await bot.set_friend_add_request(flag=request.flag, approve=False)
            except Exception as error:
                logger.warning("处理好友申请 #%s 的 OneBot API 调用失败: %r", request_id, error)
                return ReviewResult("failed", request)
            try:
                self.store.mark_handled(request, APPROVED if approve else REJECTED, handled_by)
            except Exception as error:
                logger.error("好友申请 #%s 已由 OneBot 处理，但状态保存失败: %r", request_id, error)
                return ReviewResult("failed", request)
            return ReviewResult("success", request)


def _qq_user_id(superuser: Any) -> int:
    """Accept normal QQ IDs and NoneBot adapter-prefixed SUPERUSER entries."""
    return int(str(superuser).rsplit(":", 1)[-1])


def notification_text(request: FriendRequest) -> str:
    return (
        "收到新的好友申请\n\n"
        f"编号：#{request.request_id}\nQQ：{request.user_id}\n"
        f"验证信息：{request.comment}\n接收 Bot：{request.bot_id}\n时间：{request.created_at}\n\n"
        f"同意：\n/好友同意 {request.request_id}\n\n"
        f"同意并设置备注：\n/好友同意 {request.request_id} 张三\n\n"
        f"拒绝：\n/好友拒绝 {request.request_id}"
    )


default_service = FriendRequestService(FriendRequestStore())
