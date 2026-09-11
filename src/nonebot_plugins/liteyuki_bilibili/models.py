"""Normalized Bilibili domain models shared by every feature module."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


BilibiliEventKind = Literal["dynamic", "video", "live_start", "live_end"]
BilibiliTargetType = Literal["group", "private"]


class BilibiliNav(BaseModel):
    is_login: bool = False
    mid: str = ""
    username: str = ""


class BilibiliUser(BaseModel):
    uid: str
    name: str = ""
    avatar_url: str = ""


class BilibiliVideo(BaseModel):
    aid: str = ""
    bvid: str = ""
    title: str = ""
    description: str = ""
    url: str = ""
    cover_url: str = ""
    author_name: str = ""
    author_uid: str = ""
    timestamp: datetime | None = None
    metrics: dict[str, int | str] = Field(default_factory=dict)


class BilibiliLiveStatus(BaseModel):
    uid: str
    room_id: str = ""
    live: bool = False
    title: str = ""
    area_name: str = ""
    cover_url: str = ""
    url: str = ""


class BilibiliQRCode(BaseModel):
    url: str
    key: str


class BilibiliQRLoginResult(BaseModel):
    status: Literal["waiting", "scanned", "confirmed", "expired"]
    cookie: str = ""
    refresh_token: str = ""


class BilibiliEvent(BaseModel):
    """A renderable event, independent of its source endpoint."""

    kind: BilibiliEventKind
    uid: str
    event_id: str
    title: str = ""
    body: str = ""
    url: str = ""
    author_name: str = ""
    avatar_url: str = ""
    cover_urls: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None
    metrics: dict[str, int | str] = Field(default_factory=dict)


class BilibiliSubscription(BaseModel):
    """One target's independently consumed subscription state for an UP."""

    target_type: BilibiliTargetType
    target_id: str
    uid: str
    dynamic_enabled: bool = True
    video_enabled: bool = True
    live_enabled: bool = True
    at_all: bool = False
    created_by: str = ""
    created_at: datetime
    updated_at: datetime
    last_dynamic_id: str = ""
    last_video_id: str = ""
    last_live_state: Literal["unknown", "live", "offline"] = "unknown"
