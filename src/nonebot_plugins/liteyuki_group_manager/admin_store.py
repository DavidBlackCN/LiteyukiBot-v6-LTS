"""Persistent manual Bot ADMIN overrides, independent from QQ roles."""

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from nonebot import logger


def empty_admin_overrides() -> dict:
    return {"groups": {}}


def validate_admin_overrides(raw: object) -> dict:
    if not isinstance(raw, dict) or set(raw) != {"groups"} or not isinstance(raw["groups"], dict):
        raise ValueError("invalid Bot ADMIN override format")
    result = empty_admin_overrides()
    for group_id, values in raw["groups"].items():
        if not isinstance(group_id, str) or not group_id or not isinstance(values, dict):
            raise ValueError("invalid Bot ADMIN group override")
        if set(values) != {"grant", "deny"}:
            raise ValueError("invalid Bot ADMIN override keys")
        grant, deny = values["grant"], values["deny"]
        if (not isinstance(grant, list) or not isinstance(deny, list)
                or any(not isinstance(item, str) or not item for item in grant + deny)
                or set(grant) & set(deny)):
            raise ValueError("invalid Bot ADMIN user override")
        result["groups"][group_id] = {"grant": sorted(set(grant)), "deny": sorted(set(deny))}
    return result


class BotAdminOverrideStore:
    """File-backed manual overrides. A damaged file is never overwritten."""

    def __init__(self, path: Path):
        self.path = path
        self.overrides = empty_admin_overrides()
        self.storage_error: str | None = None

    def load(self) -> None:
        try:
            if self.path.exists():
                self.overrides = validate_admin_overrides(json.loads(self.path.read_text(encoding="utf-8")))
            else:
                self._write(self.overrides)
            self.storage_error = None
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
            self.storage_error = str(error)
            self.overrides = empty_admin_overrides()
            logger.error(f"Bot ADMIN 覆盖规则加载失败，保留原文件并按自动继承处理：{error}")

    def _write(self, overrides: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix="admins-", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                json.dump(overrides, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def _change(self, operation: Callable[[dict], None]) -> None:
        if self.storage_error:
            raise ValueError("Bot ADMIN 覆盖文件异常，请修复 admins.json 并重启")
        candidate = copy.deepcopy(self.overrides)
        operation(candidate)
        candidate = validate_admin_overrides(candidate)
        self._write(candidate)
        self.overrides = candidate

    def get_override(self, group_id: int | str, user_id: int | str) -> bool | None:
        group = self.overrides["groups"].get(str(group_id), {})
        user_id = str(user_id)
        if user_id in group.get("deny", []):
            return False
        if user_id in group.get("grant", []):
            return True
        return None

    def set_override(self, group_id: int | str, user_id: int | str, granted: bool) -> None:
        group_id, user_id = str(group_id), str(user_id)
        def update(overrides: dict) -> None:
            group = overrides["groups"].setdefault(group_id, {"grant": [], "deny": []})
            for key in ("grant", "deny"):
                group[key] = [item for item in group[key] if item != user_id]
            group["grant" if granted else "deny"].append(user_id)
        self._change(update)

    def reset_override(self, group_id: int | str, user_id: int | str) -> None:
        group_id, user_id = str(group_id), str(user_id)
        def update(overrides: dict) -> None:
            group = overrides["groups"].get(group_id)
            if not group:
                return
            for key in ("grant", "deny"):
                group[key] = [item for item in group[key] if item != user_id]
            if not group["grant"] and not group["deny"]:
                del overrides["groups"][group_id]
        self._change(update)

    def group_overrides(self, group_id: int | str) -> dict[str, list[str]]:
        group = self.overrides["groups"].get(str(group_id), {"grant": [], "deny": []})
        return {"grant": list(group["grant"]), "deny": list(group["deny"])}
