from __future__ import annotations

from pydantic import Field

from src.utils.base.data import Database, LiteModel


class LuckUsage(LiteModel):
    TABLE_NAME: str = "sixty_api_luck_usage"
    user_id: str = Field(default="")
    date: str = Field(default="")
    count: int = Field(default=0)


luck_db = Database("data/liteyuki/60s.ldb")
luck_db.auto_migrate(LuckUsage())


def can_use_luck(user_id: str, date: str, limit: int) -> bool:
    if limit <= 0:
        return False
    item = luck_db.where_one(LuckUsage(), "user_id = ? AND date = ?", user_id, date)
    return item is None or item.count < limit


def record_luck_success(user_id: str, date: str) -> None:
    item = luck_db.where_one(LuckUsage(), "user_id = ? AND date = ?", user_id, date)
    if item is None:
        item = LuckUsage(user_id=user_id, date=date, count=0)
    item.count += 1
    luck_db.save(item)
