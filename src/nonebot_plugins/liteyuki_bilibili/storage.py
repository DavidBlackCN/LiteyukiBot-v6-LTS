"""SQLite persistence for Bilibili subscriptions and per-target cursors."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime

from .credential import BILIBILI_DATABASE_PATH
from .models import BilibiliEvent, BilibiliSubscription


class SubscriptionStore:
    """Use SQLite constraints instead of process-local de-duplication state."""

    def __init__(self, database_path: str = BILIBILI_DATABASE_PATH) -> None:
        self.database_path = database_path
        parent = os.path.dirname(database_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS bilibili_subscription ("
                "target_type TEXT NOT NULL, target_id TEXT NOT NULL, uid TEXT NOT NULL, "
                "dynamic_enabled INTEGER NOT NULL, video_enabled INTEGER NOT NULL, "
                "live_enabled INTEGER NOT NULL, at_all INTEGER NOT NULL, created_by TEXT NOT NULL, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                "last_dynamic_id TEXT NOT NULL DEFAULT '', "
                "last_video_id TEXT NOT NULL DEFAULT '', "
                "last_live_state TEXT NOT NULL DEFAULT 'unknown', "
                "UNIQUE(target_type, target_id, uid)"
                ")"
            )

    def add(
        self,
        *,
        target_type: str,
        target_id: str,
        uid: str,
        dynamic_enabled: bool = True,
        video_enabled: bool = True,
        live_enabled: bool = True,
        at_all: bool = False,
        created_by: str = "",
    ) -> tuple[BilibiliSubscription, bool]:
        """Create or update one target subscription without clearing its cursors."""
        self._validate_target(target_type, target_id, uid)
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existed = connection.execute(
                "SELECT 1 FROM bilibili_subscription "
                "WHERE target_type = ? AND target_id = ? AND uid = ?",
                (target_type, target_id, uid),
            ).fetchone()
            connection.execute(
                "INSERT INTO bilibili_subscription("
                "target_type, target_id, uid, dynamic_enabled, video_enabled, live_enabled, "
                "at_all, created_by, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(target_type, target_id, uid) DO UPDATE SET "
                "dynamic_enabled = excluded.dynamic_enabled, "
                "video_enabled = excluded.video_enabled, "
                "live_enabled = excluded.live_enabled, at_all = excluded.at_all, "
                "updated_at = excluded.updated_at",
                (
                    target_type,
                    target_id,
                    uid,
                    int(dynamic_enabled),
                    int(video_enabled),
                    int(live_enabled),
                    int(at_all),
                    created_by,
                    now,
                    now,
                ),
            )
        return self.get(target_type, target_id, uid), existed is None

    def get(self, target_type: str, target_id: str, uid: str) -> BilibiliSubscription:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM bilibili_subscription "
                "WHERE target_type = ? AND target_id = ? AND uid = ?",
                (target_type, target_id, uid),
            ).fetchone()
        if row is None:
            raise KeyError((target_type, target_id, uid))
        return _subscription(row)

    def list_target(self, target_type: str, target_id: str) -> list[BilibiliSubscription]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM bilibili_subscription WHERE target_type = ? AND target_id = ? "
                "ORDER BY uid",
                (target_type, target_id),
            ).fetchall()
        return [_subscription(row) for row in rows]

    def list_uid(self, uid: str) -> list[BilibiliSubscription]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM bilibili_subscription WHERE uid = ? ORDER BY target_type, target_id",
                (uid,),
            ).fetchall()
        return [_subscription(row) for row in rows]

    def list_active(self) -> list[BilibiliSubscription]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM bilibili_subscription "
                "WHERE dynamic_enabled = 1 OR video_enabled = 1 OR live_enabled = 1 "
                "ORDER BY uid, target_type, target_id"
            ).fetchall()
        return [_subscription(row) for row in rows]

    def remove(self, target_type: str, target_id: str, uid: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM bilibili_subscription "
                "WHERE target_type = ? AND target_id = ? AND uid = ?",
                (target_type, target_id, uid),
            )
        return cursor.rowcount > 0

    def initialize_baseline(
        self,
        target_type: str,
        target_id: str,
        uid: str,
        *,
        dynamic_id: str = "",
        video_id: str = "",
        live_state: str = "unknown",
    ) -> BilibiliSubscription:
        """Set cursors once so a newly added target never emits old content."""
        if live_state not in {"unknown", "live", "offline"}:
            raise ValueError("live_state must be unknown, live, or offline")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE bilibili_subscription SET "
                "last_dynamic_id = CASE WHEN last_dynamic_id = '' THEN ? ELSE last_dynamic_id END, "
                "last_video_id = CASE WHEN last_video_id = '' THEN ? ELSE last_video_id END, "
                "last_live_state = CASE WHEN last_live_state = 'unknown' THEN ? ELSE last_live_state END, "
                "updated_at = ? WHERE target_type = ? AND target_id = ? AND uid = ?",
                (dynamic_id, video_id, live_state, _now(), target_type, target_id, uid),
            )
        if cursor.rowcount == 0:
            raise KeyError((target_type, target_id, uid))
        return self.get(target_type, target_id, uid)

    def record_delivery(
        self, target_type: str, target_id: str, uid: str, event: BilibiliEvent
    ) -> BilibiliSubscription:
        """Advance only this target after the send layer confirms delivery."""
        if str(event.uid) != str(uid):
            raise ValueError("event uid does not match subscription uid")
        field, value = _cursor_update(event)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE bilibili_subscription SET {field} = ?, updated_at = ? "
                "WHERE target_type = ? AND target_id = ? AND uid = ?",
                (value, _now(), target_type, target_id, uid),
            )
        if cursor.rowcount == 0:
            raise KeyError((target_type, target_id, uid))
        return self.get(target_type, target_id, uid)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _validate_target(target_type: str, target_id: str, uid: str) -> None:
        if target_type not in {"group", "private"}:
            raise ValueError("target_type must be group or private")
        if not str(target_id).strip() or not str(uid).strip():
            raise ValueError("target_id and uid must not be empty")


def _cursor_update(event: BilibiliEvent) -> tuple[str, str]:
    if event.kind == "dynamic":
        return "last_dynamic_id", event.event_id
    if event.kind == "video":
        return "last_video_id", event.event_id
    return "last_live_state", "live" if event.kind == "live_start" else "offline"


def _subscription(row: sqlite3.Row) -> BilibiliSubscription:
    return BilibiliSubscription(
        target_type=row["target_type"],
        target_id=row["target_id"],
        uid=row["uid"],
        dynamic_enabled=bool(row["dynamic_enabled"]),
        video_enabled=bool(row["video_enabled"]),
        live_enabled=bool(row["live_enabled"]),
        at_all=bool(row["at_all"]),
        created_by=row["created_by"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_dynamic_id=row["last_dynamic_id"],
        last_video_id=row["last_video_id"],
        last_live_state=row["last_live_state"],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
