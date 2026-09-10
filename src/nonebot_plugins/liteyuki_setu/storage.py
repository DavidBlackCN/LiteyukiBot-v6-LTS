from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .config import SetuConfig

NAMESPACE = "liteyuki_setu"


@dataclass(frozen=True)
class GroupSettings:
    enabled: bool
    auto_recall: bool
    recall_seconds: int
    default_count: int
    provider: str
    exclude_ai: bool
    cooldown_seconds: int
    daily_image_limit_per_user: int


def group_allowed(config: SetuConfig, group_id: str | int | None) -> bool:
    """Return whether a group is included by the deployment-level list mode."""
    if group_id is None:
        return True
    listed = str(group_id) in {str(item) for item in config.setu_enabled_groups}
    return listed if config.setu_group_mode == "whitelist" else not listed


def default_settings(config: SetuConfig, group_id: str | None = None) -> GroupSettings:
    enabled = bool(group_id and group_allowed(config, group_id))
    return GroupSettings(enabled=enabled, auto_recall=config.setu_auto_recall,
                         recall_seconds=config.setu_recall_seconds, default_count=config.setu_default_count,
                         provider=config.setu_default_provider, exclude_ai=config.setu_exclude_ai,
                         cooldown_seconds=config.setu_cooldown_seconds,
                         daily_image_limit_per_user=config.setu_daily_image_limit_per_user)


def _group_model(group_id: str):
    from src.utils.base.data_manager import Group, group_db
    group = group_db.where_one(Group(), "group_id = ?", str(group_id))
    return Group, group_db, group or Group(group_id=str(group_id))


def get_group_settings(group_id: str, config: SetuConfig) -> GroupSettings:
    _, _, group = _group_model(group_id)
    values = group.config.get(NAMESPACE, {}) if isinstance(group.config, dict) else {}
    if not isinstance(values, dict):
        values = {}
    defaults = asdict(default_settings(config, group_id))
    defaults.update({key: value for key, value in values.items() if key in defaults})
    defaults["default_count"] = min(max(int(defaults["default_count"]), 1), config.setu_max_count)
    defaults["recall_seconds"] = min(max(int(defaults["recall_seconds"]), 5), 600)
    defaults["cooldown_seconds"] = min(max(int(defaults["cooldown_seconds"]), 0), 3600)
    defaults["daily_image_limit_per_user"] = min(max(int(defaults["daily_image_limit_per_user"]), 0), 1000)
    if defaults["provider"] not in {"auto", "lolicon", "mirlkoi"}:
        defaults["provider"] = config.setu_default_provider
    return GroupSettings(**defaults)


def update_group_settings(group_id: str, config: SetuConfig, **changes: Any) -> GroupSettings:
    _, group_db, group = _group_model(group_id)
    previous = get_group_settings(group_id, config)
    allowed = set(asdict(previous))
    values = asdict(previous)
    values.update({key: value for key, value in changes.items() if key in allowed})
    group_config = dict(group.config) if isinstance(group.config, dict) else {}
    group_config[NAMESPACE] = values
    group.config = group_config
    group_db.save(group)
    return GroupSettings(**values)


def reset_group_settings(group_id: str, config: SetuConfig) -> GroupSettings:
    _, group_db, group = _group_model(group_id)
    group_config = dict(group.config) if isinstance(group.config, dict) else {}
    group_config.pop(NAMESPACE, None)
    group.config = group_config
    group_db.save(group)
    return default_settings(config, group_id)