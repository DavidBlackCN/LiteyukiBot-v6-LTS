"""One safe credential source for every Bilibili feature."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .errors import BilibiliCookieFormatError


BILIBILI_DATABASE_PATH = os.path.join("data", "liteyuki", "bilibili.ldb")


def parse_cookie(value: str) -> dict[str, str]:
    """Parse a Cookie header without exposing malformed values in logs."""
    cookies: dict[str, str] = {}
    has_content = bool(value and value.strip())
    for fragment in (value or "").split(";"):
        fragment = fragment.strip()
        if not fragment or "=" not in fragment:
            continue
        key, cookie_value = fragment.split("=", 1)
        key = key.strip()
        cookie_value = cookie_value.strip()
        if not key or any(character.isspace() for character in key):
            continue
        cookies[key] = cookie_value
    if has_content and not cookies:
        raise BilibiliCookieFormatError("Cookie does not contain a valid key/value pair")
    return cookies


def serialize_cookie(cookies: Mapping[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items())


def describe_cookie(cookies: Mapping[str, str]) -> str:
    """Return a log-safe credential description containing keys only."""
    return ", ".join(cookies) if cookies else "anonymous"


@dataclass(frozen=True)
class BilibiliCredential:
    cookies: dict[str, str]
    source: str

    @property
    def cookie_header(self) -> str:
        return serialize_cookie(self.cookies)

    @property
    def is_anonymous(self) -> bool:
        return not self.cookies


class CredentialStore(Protocol):
    def load(self) -> str: ...

    def save(self, cookie: str) -> None: ...

    def clear(self) -> None: ...


class SQLiteCredentialStore:
    """Small SQLite store that never delegates secret values to debug logging."""

    def __init__(self, database_path: str = BILIBILI_DATABASE_PATH) -> None:
        self.database_path = database_path
        parent = os.path.dirname(database_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS bilibili_credential "
                "(name TEXT PRIMARY KEY, cookie TEXT NOT NULL)"
            )

    def load(self) -> str:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT cookie FROM bilibili_credential WHERE name = ?", ("default",)
            ).fetchone()
        return str(row[0]) if row else ""

    def save(self, cookie: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO bilibili_credential(name, cookie) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET cookie = excluded.cookie",
                ("default", cookie),
            )

    def clear(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM bilibili_credential WHERE name = ?", ("default",))


class CredentialManager:
    """Resolve config Cookie, persisted QR Cookie, or anonymous access."""

    def __init__(self, config_cookie: str = "", store: CredentialStore | None = None) -> None:
        self._config_cookie = config_cookie or ""
        self._store = store or SQLiteCredentialStore()

    def get(self) -> BilibiliCredential:
        if self._config_cookie.strip():
            return BilibiliCredential(parse_cookie(self._config_cookie), "config")
        stored_cookie = self._store.load()
        if stored_cookie.strip():
            return BilibiliCredential(parse_cookie(stored_cookie), "database")
        return BilibiliCredential({}, "anonymous")

    def save_qr_cookie(self, cookie: str) -> BilibiliCredential:
        credential = BilibiliCredential(parse_cookie(cookie), "database")
        if credential.is_anonymous:
            raise BilibiliCookieFormatError("QR login did not return a Cookie")
        self._store.save(credential.cookie_header)
        return credential

    def logout(self) -> None:
        """Remove only QR-persisted state; explicit config still takes precedence."""
        self._store.clear()
