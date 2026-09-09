from __future__ import annotations

from dataclasses import dataclass

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