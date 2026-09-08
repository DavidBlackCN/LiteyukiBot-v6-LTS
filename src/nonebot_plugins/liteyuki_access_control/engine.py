"""Adapter-independent rules and sliding-window accounting (single process)."""

import copy
import json
import math
import os
import tempfile
import time
from collections import deque
from pathlib import Path

from nonebot import logger

from .config import AccessControlConfig


def empty_rules():
    return {
        "version": 1,
        "blacklist_user": [], "blacklist_group": [],
        "whitelist_user": [], "whitelist_group": [],
        "user_plugins": {}, "group_plugins": {}, "limits": {},
    }


def validate_rules(raw):
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError("unsupported rules format/version")
    result = empty_rules()
    for key in ("blacklist_user", "blacklist_group", "whitelist_user", "whitelist_group"):
        values = raw.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
            raise ValueError(f"invalid {key}")
        result[key] = sorted(set(values))
    for key in ("user_plugins", "group_plugins"):
        values = raw.get(key, {})
        if not isinstance(values, dict):
            raise ValueError(f"invalid {key}")
        for subject, plugins in values.items():
            if not subject or not isinstance(plugins, dict):
                raise ValueError(f"invalid {key} subject")
            if any(not name or type(enabled) is not bool for name, enabled in plugins.items()):
                raise ValueError(f"invalid {key} plugin rule")
        result[key] = values
    limits = raw.get("limits", {})
    if not isinstance(limits, dict):
        raise ValueError("invalid limits")
    for name, limit in limits.items():
        if not name or not isinstance(limit, dict):
            raise ValueError("invalid limit")
        validate_limit(limit.get("count"), limit.get("window"))
    result["limits"] = limits
    return copy.deepcopy(result)


def validate_limit(count, window):
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError("次数须为 1–10000 的整数")
    if type(window) not in (int, float) or not math.isfinite(window) or not 0 < window <= 604800:
        raise ValueError("窗口须大于 0 且不超过 604800 秒")


class AccessController:
    def __init__(self, config: AccessControlConfig, *, clock=time.monotonic):
        self.config = config
        self.path = Path(config.access_control_data_path) / "rules.json"
        self.rules = empty_rules()
        self.clock = clock
        self.buckets = {}
        self.last_cleanup = clock()
        self.storage_error = None

    @property
    def protected(self):
        return {"liteyuki_access_control", *self.config.access_control_protected_plugins}

    def load(self):
        try:
            if self.path.exists():
                self.rules = validate_rules(json.loads(self.path.read_text(encoding="utf-8")))
            else:
                self._write(self.rules)
            self.storage_error = None
        except (OSError, ValueError, UnicodeError) as error:
            # Preserve damaged files for recovery; updates are refused until repaired.
            self.storage_error = str(error)
            self.rules = empty_rules()
            logger.error(f"访问控制规则加载失败，保留原文件并使用默认规则：{error}")

    def _write(self, rules):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix="rules-", suffix=".tmp", delete=False,
            ) as stream:
                temporary = stream.name
                json.dump(rules, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def change(self, operation):
        if self.storage_error:
            raise ValueError("规则文件异常，请先修复 rules.json 并重启")
        candidate = copy.deepcopy(self.rules)
        operation(candidate)
        candidate = validate_rules(candidate)
        self._write(candidate)
        self.rules = candidate

    def set_plugin(self, plugin, subject, *, scope="group", enabled=True):
        if scope not in ("user", "group") or not plugin or not str(subject):
            raise ValueError("插件、主体或作用域无效")
        if plugin in self.protected:
            raise ValueError("受保护插件不能设置访问规则")
        self.change(lambda rules: rules[f"{scope}_plugins"].setdefault(str(subject), {}).update({plugin: enabled}))

    def set_list(self, subject, *, scope="user", whitelist=False, remove=False):
        if scope not in ("user", "group") or not str(subject):
            raise ValueError("主体或作用域无效")
        key = f"{'whitelist' if whitelist else 'blacklist'}_{scope}"
        def update(rules):
            entries = set(rules[key])
            entries.discard(str(subject)) if remove else entries.add(str(subject))
            rules[key] = sorted(entries)
        self.change(update)

    def set_limit(self, plugin, count=None, window=None):
        if not plugin or plugin in self.protected:
            raise ValueError("受保护插件或无效插件不能设置限流")
        if count is not None:
            validate_limit(count, window)
        def update(rules):
            if count is None:
                rules["limits"].pop(plugin, None)
            else:
                rules["limits"][plugin] = {"count": count, "window": window}
        self.change(update)
        self.buckets = {k: v for k, v in self.buckets.items() if k[1] != plugin}

    def bypass(self, plugin, superuser):
        return (
            not self.config.access_control_enabled
            or plugin in self.protected
            or (superuser and self.config.access_control_superuser_bypass)
        )

    def allowed(self, plugin, user=None, group=None, *, superuser=False):
        if self.bypass(plugin, superuser):
            return True
        user = str(user) if user is not None else None
        group = str(group) if group is not None else None
        rules = self.rules
        # Explicit denial always wins over whitelist and explicit enabling.
        if user in rules["blacklist_user"] or group in rules["blacklist_group"]:
            return False
        user_rule = rules["user_plugins"].get(user, {}).get(plugin)
        group_rule = rules["group_plugins"].get(group, {}).get(plugin)
        if user_rule is False or group_rule is False:
            return False
        if user_rule is True or group_rule is True:
            return True
        if user in rules["whitelist_user"] or group in rules["whitelist_group"]:
            return True
        return self.config.access_control_default_allow

    def cleanup(self):
        now = self.clock()
        for key, timestamps in list(self.buckets.items()):
            limit = self.rules["limits"].get(key[1])
            if limit:
                while timestamps and timestamps[0] <= now - limit["window"]:
                    timestamps.popleft()
            if not limit or not timestamps:
                del self.buckets[key]
        self.last_cleanup = now

    def rate_allowed(self, plugin, user=None, group=None, *, superuser=False):
        if self.bypass(plugin, superuser):
            return True
        now = self.clock()
        if now - self.last_cleanup >= 60:
            self.cleanup()
        limit = self.rules["limits"].get(plugin)
        if not limit:
            return True
        subject = ("user", str(user)) if user is not None else ("group", str(group))
        if user is None and group is None:
            return True
        key = (subject, plugin)
        timestamps = self.buckets.setdefault(key, deque())
        while timestamps and timestamps[0] <= now - limit["window"]:
            timestamps.popleft()
        if len(timestamps) >= limit["count"]:
            return False
        timestamps.append(now)
        return True
