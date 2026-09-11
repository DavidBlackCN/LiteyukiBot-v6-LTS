"""Idempotent importer for the legacy nonebot-plugin-bilibili data files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .credential import CredentialManager, parse_cookie, serialize_cookie
from .storage import SubscriptionStore


LEGACY_DATA_DIRS = (Path("data/nonebot_plugin_bilibili"), Path("data/bilibili"))


@dataclass(frozen=True)
class MigrationReport:
    source_found: bool = False
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    baseline_pending: int = 0
    credential_imported: bool = False
    credential_skipped: bool = False


def find_legacy_data_dir() -> Path | None:
    for directory in LEGACY_DATA_DIRS:
        if (directory / "subscribers.json").is_file() or (directory / "cookie.json").is_file():
            return directory
    return None


def migrate_legacy_data(
    store: SubscriptionStore,
    credentials: CredentialManager,
    legacy_dir: Path | None = None,
) -> MigrationReport:
    """Import recognized legacy JSON without deleting or rewriting its source."""
    source = legacy_dir or find_legacy_data_dir()
    if source is None or not source.is_dir():
        return MigrationReport()
    subscribers_path = source / "subscribers.json"
    imported = updated = skipped = baseline_pending = 0
    if subscribers_path.is_file():
        payload = _read_json_object(subscribers_path)
        for group_id, settings in payload.items():
            if not isinstance(settings, dict):
                skipped += 1
                continue
            uids = settings.get("uids")
            if not isinstance(uids, list):
                skipped += 1
                continue
            at_all = settings.get("atall") if isinstance(settings.get("atall"), dict) else {}
            sub_time = settings.get("sub_time") if isinstance(settings.get("sub_time"), dict) else {}
            for uid in uids:
                uid_text = str(uid).strip()
                if not uid_text or not uid_text.isdigit():
                    skipped += 1
                    continue
                old_at_all = at_all.get(str(uid), [])
                created_at = _legacy_time(sub_time.get(str(uid)))
                subscription, created = store.add(
                    target_type="group",
                    target_id=str(group_id),
                    uid=uid_text,
                    dynamic_enabled=True,
                    video_enabled=True,
                    live_enabled=True,
                    # A per-event legacy @all list cannot safely map to the new
                    # all-event boolean. Preserve only its explicit all mode.
                    at_all=isinstance(old_at_all, list) and "all" in old_at_all,
                    created_by="legacy:nonebot-plugin-bilibili",
                    created_at=created_at,
                )
                if created:
                    imported += 1
                else:
                    updated += 1
                if (
                    subscription.last_dynamic_id == ""
                    or subscription.last_video_id == ""
                    or subscription.last_live_state == "unknown"
                ):
                    baseline_pending += 1

    credential_imported, credential_skipped = _migrate_legacy_cookie(credentials, source / "cookie.json")
    return MigrationReport(
        source_found=True,
        imported=imported,
        updated=updated,
        skipped=skipped,
        baseline_pending=baseline_pending,
        credential_imported=credential_imported,
        credential_skipped=credential_skipped,
    )


def _migrate_legacy_cookie(credentials: CredentialManager, path: Path) -> tuple[bool, bool]:
    if not path.is_file() or credentials.get().source == "config":
        return False, path.is_file()
    payload = _read_json_object(path)
    raw_cookie = payload.get("cookie") or payload.get("cookies")
    if isinstance(raw_cookie, dict):
        raw_cookie = serialize_cookie({str(key): str(value) for key, value in raw_cookie.items()})
    if not isinstance(raw_cookie, str) or not raw_cookie.strip():
        return False, False
    try:
        parsed = parse_cookie(raw_cookie)
    except Exception:
        return False, True
    if not parsed:
        return False, True
    credentials.save_qr_cookie(serialize_cookie(parsed))
    return True, False


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _legacy_time(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value), UTC)
    except (TypeError, ValueError, OSError):
        return None
