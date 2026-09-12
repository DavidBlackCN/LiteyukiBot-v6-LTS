from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from pydantic import Field

from src.utils.base.data import Database, LiteModel


class LuckUsage(LiteModel):
    TABLE_NAME: str = "sixty_api_luck_usage"
    user_id: str = Field(default="")
    date: str = Field(default="")
    count: int = Field(default=0)
    last_result: bytes = Field(default=b"")


@dataclass(frozen=True)
class LuckRequest:
    should_fetch: bool
    cached_result: bytes | None = None


luck_db = Database("data/liteyuki/60s.ldb")
luck_db.auto_migrate(LuckUsage())


def begin_luck_request(user_id: str, date: str, limit: int) -> LuckRequest:
    """Count a received command; once capped, serve its last successful card."""
    item = luck_db.where_one(LuckUsage(), "user_id = ? AND date = ?", user_id, date)
    if item is not None and item.count >= limit:
        return LuckRequest(False, item.last_result or None)
    if limit <= 0:
        return LuckRequest(False, item.last_result if item else None)
    if item is None:
        item = LuckUsage(user_id=user_id, date=date)
    item.count += 1
    luck_db.save(item)
    return LuckRequest(True)


def record_luck_result(user_id: str, date: str, result: bytes) -> None:
    item = luck_db.where_one(LuckUsage(), "user_id = ? AND date = ?", user_id, date)
    if item is None:
        item = LuckUsage(user_id=user_id, date=date)
    item.last_result = result
    luck_db.save(item)


# Kept for compatibility with existing callers/tests; command handling uses
# begin_luck_request() so the persisted count represents received requests.
def can_use_luck(user_id: str, date: str, limit: int) -> bool:
    if limit <= 0:
        return False
    item = luck_db.where_one(LuckUsage(), "user_id = ? AND date = ?", user_id, date)
    return item is None or item.count < limit


def record_luck_success(user_id: str, date: str) -> None:
    item = luck_db.where_one(LuckUsage(), "user_id = ? AND date = ?", user_id, date)
    if item is None:
        item = LuckUsage(user_id=user_id, date=date)
    item.count += 1
    luck_db.save(item)

class RandomPushPlanStore:
    """Small, restart-safe store for the current daily random-push plans."""

    def __init__(self, path: Path = Path("data/liteyuki/60s_random_push.json")) -> None:
        self.path = path
        self._lock = RLock()
        self._data: dict[str, object] = {"plans": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("plans", {}), dict):
                raise ValueError("plans 字段不是对象")
            self._data = {"plans": data["plans"]}
        except Exception as exc:
            from nonebot import logger

            logger.warning("60s 随机推送状态损坏，已使用空状态重新生成：{}", repr(exc))
            self._data = {"plans": {}}

    def get(self, date: str, group_id: int, feature: str) -> dict[str, object] | None:
        with self._lock:
            try:
                plan = self._data["plans"][date][str(group_id)][feature]  # type: ignore[index]
                if not isinstance(plan, dict):
                    raise ValueError("计划不是对象")
                scheduled = plan.get("scheduled_times", [])
                sent = plan.get("sent_times", [])
                if not isinstance(scheduled, list) or not isinstance(sent, list):
                    raise ValueError("计划时间不是列表")
                return {
                    "scheduled_times": [str(value) for value in scheduled],
                    "sent_times": [str(value) for value in sent],
                    "signature": str(plan.get("signature", "")),
                }
            except (KeyError, TypeError, ValueError):
                return None

    def save(self, date: str, group_id: int, feature: str, plan: dict[str, object]) -> None:
        with self._lock:
            plans = self._data.setdefault("plans", {})
            assert isinstance(plans, dict)
            groups = plans.setdefault(date, {})
            assert isinstance(groups, dict)
            features = groups.setdefault(str(group_id), {})
            assert isinstance(features, dict)
            features[feature] = {
                "scheduled_times": [str(value) for value in plan.get("scheduled_times", [])],
                "sent_times": [str(value) for value in plan.get("sent_times", [])],
                "signature": str(plan.get("signature", "")),
            }
            self._write()

    def mark_sent(self, date: str, group_id: int, feature: str, scheduled_time: str) -> None:
        plan = self.get(date, group_id, feature)
        if plan is None:
            return
        sent = plan["sent_times"]
        assert isinstance(sent, list)
        if scheduled_time not in sent:
            sent.append(scheduled_time)
            self.save(date, group_id, feature, plan)

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


random_push_plan_store = RandomPushPlanStore()
