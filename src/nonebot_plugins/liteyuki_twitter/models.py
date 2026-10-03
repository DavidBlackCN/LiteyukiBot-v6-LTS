"""Normalized content, independent of Nitter HTML and adapter messages."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json


@dataclass
class Media:
    url: str
    kind: str = "image"


@dataclass
class Post:
    post_id: str
    account: str
    author: str = ""
    text: str = ""
    published_at: str = ""
    media: list[Media] = field(default_factory=list)
    quote: Post | None = None
    reply: bool = False
    repost: bool = False
    pinned: bool = False
    translation: str = ""
    translation_note: str = ""
    avatar_url: str = ""

    @property
    def url(self) -> str:
        return f"https://x.com/{self.account}/status/{self.post_id}"

    def dumps(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def loads(cls, value: str | dict) -> Post:
        data = json.loads(value) if isinstance(value, str) else dict(value)
        data["media"] = [Media(**item) for item in data.get("media", [])]
        if data.get("quote"):
            data["quote"] = cls.loads(data["quote"])
        return cls(**data)


class TwitterError(Exception):
    """Safe, user-facing failure text; never include credentials or raw responses."""


class SourceError(TwitterError):
    def __init__(self, message: str, *, status: int = 0, blocked: bool = False):
        super().__init__(message)
        self.status = status
        self.blocked = blocked
