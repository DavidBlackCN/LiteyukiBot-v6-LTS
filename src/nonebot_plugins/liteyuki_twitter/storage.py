"""Per-group overrides, durable queues and caches in an isolated SQLite DB."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import time

from .config import FollowOptions, TwitterConfig, normalize_account
from .models import Post

DATABASE_PATH = "data/liteyuki/twitter.ldb"


class TwitterStore:
    def __init__(self, path: str = DATABASE_PATH):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS overrides (
                    group_id TEXT, account TEXT, removed INTEGER NOT NULL,
                    media_only INTEGER, replies INTEGER, reposts INTEGER,
                    PRIMARY KEY(group_id,account));
                CREATE TABLE IF NOT EXISTS baselines (
                    group_id TEXT, account TEXT, initialized REAL NOT NULL,
                    PRIMARY KEY(group_id,account));
                CREATE TABLE IF NOT EXISTS seen (
                    group_id TEXT, account TEXT, event_key TEXT, created REAL NOT NULL,
                    PRIMARY KEY(group_id,account,event_key));
                CREATE TABLE IF NOT EXISTS queue (
                    group_id TEXT, account TEXT, event_key TEXT, payload TEXT NOT NULL,
                    created REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    next_try REAL NOT NULL DEFAULT 0, published REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(group_id,account,event_key));
                CREATE TABLE IF NOT EXISTS posts (post_id TEXT PRIMARY KEY, payload TEXT, updated REAL);
                CREATE TABLE IF NOT EXISTS translations (cache_key TEXT PRIMARY KEY, text TEXT, updated REAL);
                CREATE TABLE IF NOT EXISTS activity (group_id TEXT PRIMARY KEY, active INTEGER NOT NULL);
            """)
            if "published" not in {row[1] for row in db.execute("PRAGMA table_info(queue)")}:
                db.execute("ALTER TABLE queue ADD COLUMN published REAL NOT NULL DEFAULT 0")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def follows(self, config: TwitterConfig, group_id: str) -> dict[str, tuple[FollowOptions, str]]:
        defaults = config.twitter_group_follows.get(str(group_id), config.twitter_follows)
        result = {item.account: (item, "配置") for item in defaults}
        with self.connect() as db:
            rows = db.execute("SELECT * FROM overrides WHERE group_id=?", (str(group_id),)).fetchall()
        for row in rows:
            if row["removed"]:
                result.pop(row["account"], None)
            else:
                result[row["account"]] = (FollowOptions(account=row["account"], media_only=bool(row["media_only"]),
                                                         replies=bool(row["replies"]), reposts=bool(row["reposts"])), "群内覆盖")
        return result

    def follow(self, group_id: str, options: FollowOptions):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO overrides VALUES(?,?,?,?,?,?)",
                       (str(group_id), options.account, 0, int(options.media_only), int(options.replies), int(options.reposts)))

    def unfollow(self, group_id: str, account: str):
        account = normalize_account(account)
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO overrides VALUES(?,?,1,0,0,0)", (str(group_id), account))
            self._clear_account(db, str(group_id), account)

    def _clear_account(self, db, group_id, account):
        for table in ("baselines", "seen", "queue"):
            db.execute(f"DELETE FROM {table} WHERE group_id=? AND account=?", (group_id, account))

    def reset(self, group_id: str):
        with self.connect() as db:
            db.execute("DELETE FROM overrides WHERE group_id=?", (str(group_id),))
            for table in ("baselines", "seen", "queue"):
                db.execute(f"DELETE FROM {table} WHERE group_id=?", (str(group_id),))

    def set_active(self, group_id: str, active: bool):
        """Activation always discards paused history, including pre-pause queue."""
        with self.connect() as db:
            previous = db.execute("SELECT active FROM activity WHERE group_id=?", (str(group_id),)).fetchone()
            if active and (previous is None or not previous[0]):
                for table in ("baselines", "seen", "queue"):
                    db.execute(f"DELETE FROM {table} WHERE group_id=?", (str(group_id),))
            db.execute("INSERT OR REPLACE INTO activity VALUES(?,?)", (str(group_id), int(active)))

    @staticmethod
    def key(post: Post) -> str:
        return f"{'repost' if post.repost else 'post'}:{post.post_id}"

    def window_gap(self, group_id: str, account: str, posts: list[Post]) -> bool:
        ids = [int(post.post_id) for post in posts if not post.pinned and not post.repost]
        if not ids:
            return False
        with self.connect() as db:
            row = db.execute("SELECT MAX(CAST(substr(event_key,6) AS INTEGER)) FROM seen WHERE group_id=? AND account=? AND event_key LIKE 'post:%'",
                             (str(group_id), account)).fetchone()
        return row[0] is not None and min(ids) > row[0]

    def ingest(self, group_id: str, options: FollowOptions, posts: list[Post]) -> int:
        """Atomically baseline or queue events before committing discovery state."""
        now, group_id = time.time(), str(group_id)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            baseline = db.execute("SELECT initialized FROM baselines WHERE group_id=? AND account=?", (group_id, options.account)).fetchone()
            latest = db.execute("SELECT MAX(CAST(substr(event_key,instr(event_key,':')+1) AS INTEGER)) FROM seen WHERE group_id=? AND account=?", (group_id, options.account)).fetchone()[0]
            count = 0
            for post in posts:
                key = self.key(post)
                known = db.execute("SELECT 1 FROM seen WHERE group_id=? AND account=? AND event_key=?", (group_id, options.account, key)).fetchone()
                if known:
                    continue
                db.execute("INSERT INTO seen VALUES(?,?,?,?)", (group_id, options.account, key, now))
                db.execute("INSERT OR REPLACE INTO posts VALUES(?,?,?)", (post.post_id, post.dumps(), now))
                if baseline is None or post.pinned:
                    continue
                # Reposts have older original IDs; RSS publication time is used.
                if post.published_at:
                    try:
                        if datetime.fromisoformat(post.published_at).timestamp() <= baseline[0]:
                            continue
                    except ValueError:
                        continue
                elif latest is None or int(post.post_id) <= latest:
                    continue
                if (post.reply and not options.replies) or (post.repost and not options.reposts):
                    continue
                if options.media_only and not (post.media or (post.quote and post.quote.media)):
                    continue
                published = datetime.fromisoformat(post.published_at).timestamp() if post.published_at else now
                db.execute("INSERT OR IGNORE INTO queue(group_id,account,event_key,payload,created,published) VALUES(?,?,?,?,?,?)",
                           (group_id, options.account, key, post.dumps(), now, published))
                count += 1
            if baseline is None:
                db.execute("INSERT INTO baselines VALUES(?,?,?)", (group_id, options.account, now))
            return count

    def pending(self, group_id: str):
        with self.connect() as db:
            db.execute("DELETE FROM queue WHERE created<? OR attempts>=3", (time.time() - 86400,))
            rows = db.execute("SELECT * FROM queue WHERE group_id=? AND next_try<=? ORDER BY published, CAST(substr(event_key,instr(event_key,':')+1) AS INTEGER) LIMIT 5",
                              (str(group_id), time.time())).fetchall()
        return rows

    def finish(self, row, success: bool):
        params = (row["group_id"], row["account"], row["event_key"])
        with self.connect() as db:
            if success:
                db.execute("DELETE FROM queue WHERE group_id=? AND account=? AND event_key=?", params)
            else:
                db.execute("UPDATE queue SET attempts=attempts+1,next_try=? WHERE group_id=? AND account=? AND event_key=?",
                           (time.time() + 60 * 2 ** row["attempts"], *params))

    def pending_count(self, group_id):
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM queue WHERE group_id=?", (str(group_id),)).fetchone()[0]

    def prune_accounts(self, group_id: str, accounts):
        with self.connect() as db:
            for row in db.execute("SELECT account FROM baselines WHERE group_id=?", (str(group_id),)).fetchall():
                if row[0] not in accounts:
                    self._clear_account(db, str(group_id), row[0])

    def cached_post(self, post_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM posts WHERE post_id=? AND updated>?", (post_id, time.time() - 86400)).fetchone()
        return Post.loads(row[0]) if row else None

    def cache_post(self, post: Post):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO posts VALUES(?,?,?)", (post.post_id, post.dumps(), time.time()))

    def translation(self, key: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT text FROM translations WHERE cache_key=? AND updated>?", (key, time.time() - 7 * 86400)).fetchone()
        return row[0] if row else None

    def save_translation(self, key, text):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO translations VALUES(?,?,?)", (key, text, time.time()))

    def cleanup(self):
        with self.connect() as db:
            db.execute("DELETE FROM posts WHERE updated<?", (time.time() - 7 * 86400,))
            db.execute("DELETE FROM translations WHERE updated<?", (time.time() - 7 * 86400,))
            db.execute("DELETE FROM queue WHERE created<? OR attempts>=3", (time.time() - 86400,))
