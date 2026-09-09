from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field

from src.utils.base.data import Database, LiteModel


class DailyImageUsage(LiteModel):
    TABLE_NAME: str = "setu_daily_image_usage"
    group_id: str = Field(default="")
    user_id: str = Field(default="")
    date: str = Field(default="")
    count: int = Field(default=0)


class PrivateR18Settings(LiteModel):
    TABLE_NAME: str = "setu_private_r18_settings"
    setting_key: str = Field(default="default")
    enabled: bool = Field(default=False)
    allowed_user_ids: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PrivateR18Access:
    enabled: bool
    allowed_user_ids: set[str]


quota_db = Database("data/liteyuki/setu.ldb")
quota_db.auto_migrate(DailyImageUsage(), PrivateR18Settings())


def get_usage(group_id: str, user_id: str, date: str) -> int:
    item = quota_db.where_one(
        DailyImageUsage(), "group_id = ? AND user_id = ? AND date = ?", group_id, user_id, date,
    )
    return int(item.count) if item is not None else 0


def has_quota(group_id: str, user_id: str, date: str, *, limit: int, requested: int) -> bool:
    return limit <= 0 or get_usage(group_id, user_id, date) + requested <= limit


def record_success(group_id: str, user_id: str, date: str, count: int = 1) -> int:
    if count <= 0:
        return get_usage(group_id, user_id, date)
    item = quota_db.where_one(
        DailyImageUsage(), "group_id = ? AND user_id = ? AND date = ?", group_id, user_id, date,
    )
    if item is None:
        item = DailyImageUsage(group_id=group_id, user_id=user_id, date=date)
    item.count += count
    quota_db.save(item)
    return item.count


def _r18_item() -> PrivateR18Settings | None:
    return quota_db.where_one(PrivateR18Settings(), "setting_key = ?", "default")


def get_private_r18_access(config) -> PrivateR18Access:
    item = _r18_item()
    enabled = item.enabled if item is not None else bool(config.setu_private_r18_enabled)
    configured = {str(user_id) for user_id in config.setu_private_r18_user_ids}
    dynamic = set(item.allowed_user_ids) if item is not None else set()
    return PrivateR18Access(enabled=enabled, allowed_user_ids=configured | dynamic)


def set_private_r18_enabled(enabled: bool, config) -> PrivateR18Access:
    item = _r18_item() or PrivateR18Settings()
    item.enabled = enabled
    quota_db.save(item)
    return get_private_r18_access(config)


def add_private_r18_user(user_id: str, config) -> PrivateR18Access:
    item = _r18_item() or PrivateR18Settings()
    item.allowed_user_ids = sorted(set(item.allowed_user_ids) | {str(user_id)})
    quota_db.save(item)
    return get_private_r18_access(config)


def remove_private_r18_user(user_id: str, config) -> PrivateR18Access:
    item = _r18_item() or PrivateR18Settings()
    item.allowed_user_ids = [item_id for item_id in item.allowed_user_ids if item_id != str(user_id)]
    quota_db.save(item)
    return get_private_r18_access(config)