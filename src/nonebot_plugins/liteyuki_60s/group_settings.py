"""Group-scoped 60s settings backed by the existing ``Group.config`` field."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .config import SixtyApiConfig
from .service import enabled, group_allowed

NAMESPACE = "liteyuki_60s"
FEATURE_ALIASES = {
    "60s": "world", "AI资讯": "ai", "历史上的今天": "history", "IT资讯": "it",
    "摸鱼日报": "moyu", "一言": "hitokoto", "运势": "luck", "发病文学": "fabing",
    "KFC": "kfc", "冷笑话": "dad_joke",
}
FEATURES = tuple(FEATURE_ALIASES.values())
PUSH_FEATURES = ("world", "ai", "history", "it", "moyu", "kfc")
RANDOM_FEATURES = ("fabing", "dad_joke")


def _group_model(group_id: str):
    from src.utils.base.data_manager import Group, group_db

    group = group_db.where_one(Group(), "group_id = ?", str(group_id))
    return group_db, group or Group(group_id=str(group_id))


def get_group_overrides(group_id: str | int) -> dict[str, Any]:
    """Return a copy of this group's raw 60s override, or an empty mapping."""
    _, group = _group_model(str(group_id))
    values = group.config.get(NAMESPACE, {}) if isinstance(group.config, dict) else {}
    return deepcopy(values) if isinstance(values, dict) else {}


def get_group_settings(group_id: str | int, config: SixtyApiConfig) -> dict[str, Any]:
    """Return the final, group-aware view used for management status output."""
    overrides = get_group_overrides(group_id)
    return {
        "allowed": group_allowed(config, group_id),
        "enabled": bool(overrides.get("enabled", True)),
        "features": {
            feature: feature_allowed(config, group_id, feature)
            for feature in FEATURES
        },
        "push": {
            feature: resolve_push_settings(config, group_id, feature)
            for feature in PUSH_FEATURES
        },
        "random_push": {
            feature: resolve_random_push_settings(config, group_id, feature)
            for feature in RANDOM_FEATURES
        },
        "overrides": overrides,
    }


def _nested(overrides: dict[str, Any], section: str, feature: str) -> dict[str, Any]:
    values = overrides.get(section, {})
    if not isinstance(values, dict):
        return {}
    value = values.get(feature, {})
    return value if isinstance(value, dict) else {}


def feature_allowed(config: SixtyApiConfig, group_id: str | int | None, feature: str) -> bool:
    """Resolve deployment boundary, global switch and current group overrides."""
    if feature not in FEATURES or not enabled(config, feature):
        return False
    if group_id is None:
        return True
    if not group_allowed(config, group_id):
        return False
    overrides = get_group_overrides(group_id)
    if not bool(overrides.get("enabled", True)):
        return False
    features = overrides.get("features", {})
    value = features.get(feature, True) if isinstance(features, dict) else True
    if isinstance(value, dict):
        value = value.get("enabled", True)
    return value is not False


def resolve_push_settings(config: SixtyApiConfig, group_id: str | int, feature: str) -> dict[str, Any]:
    if feature not in PUSH_FEATURES:
        raise KeyError(feature)
    override = _nested(get_group_overrides(group_id), "push", feature)
    return {
        "enabled": feature_allowed(config, group_id, feature)
        and bool(override.get("enabled", getattr(config, f"sixty_api_{feature}_push_enabled"))),
        "time": str(override.get("time", getattr(config, f"sixty_api_{feature}_push_time"))),
        "overridden": bool(override),
    }


def resolve_random_push_settings(config: SixtyApiConfig, group_id: str | int, feature: str) -> dict[str, Any]:
    if feature not in RANDOM_FEATURES:
        raise KeyError(feature)
    override = _nested(get_group_overrides(group_id), "random_push", feature)
    return {
        "enabled": feature_allowed(config, group_id, feature)
        and bool(override.get("enabled", getattr(config, f"sixty_api_{feature}_random_push_enabled"))),
        "daily_min": int(override.get("daily_min", getattr(config, f"sixty_api_{feature}_random_daily_min"))),
        "daily_max": int(override.get("daily_max", getattr(config, f"sixty_api_{feature}_random_daily_max"))),
        "start": str(override.get("start", getattr(config, f"sixty_api_{feature}_random_start"))),
        "end": str(override.get("end", getattr(config, f"sixty_api_{feature}_random_end"))),
        "overridden": bool(override),
    }


def update_group_settings(group_id: str | int, config: SixtyApiConfig, **changes: Any) -> dict[str, Any]:
    """Persist only declared group overrides; deployment fields are never accepted."""
    group_db, group = _group_model(str(group_id))
    values = get_group_overrides(group_id)
    if "enabled" in changes:
        values["enabled"] = bool(changes["enabled"])
    for section, allowed in (("features", FEATURES), ("push", PUSH_FEATURES), ("random_push", RANDOM_FEATURES)):
        incoming = changes.get(section)
        if not isinstance(incoming, dict):
            continue
        target = values.setdefault(section, {})
        if not isinstance(target, dict):
            target = values[section] = {}
        for feature, update in incoming.items():
            if feature not in allowed or not isinstance(update, dict):
                continue
            if section == "features":
                if "enabled" in update:
                    target[feature] = bool(update["enabled"])
                continue
            permitted = {"enabled"}
            if section == "push":
                permitted.add("time")
            else:
                permitted.update({"daily_min", "daily_max", "start", "end"})
            item = target.setdefault(feature, {})
            if not isinstance(item, dict):
                item = target[feature] = {}
            item.update({key: value for key, value in update.items() if key in permitted})
    group_config = dict(group.config) if isinstance(group.config, dict) else {}
    group_config[NAMESPACE] = values
    group.config = group_config
    group_db.save(group)
    return get_group_settings(group_id, config)


def reset_group_settings(group_id: str | int, config: SixtyApiConfig) -> dict[str, Any]:
    group_db, group = _group_model(str(group_id))
    group_config = dict(group.config) if isinstance(group.config, dict) else {}
    group_config.pop(NAMESPACE, None)
    group.config = group_config
    group_db.save(group)
    return get_group_settings(group_id, config)
