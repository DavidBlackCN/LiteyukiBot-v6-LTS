"""Static deployment settings; group overrides are persisted separately."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


def normalize_account(value: str) -> str:
    value = value.strip().lstrip("@").lower()
    if not re.fullmatch(r"[a-z0-9_]{1,15}", value):
        raise ValueError("账号须为 1-15 位英文字母、数字或下划线")
    return value


def service_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return value
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("服务地址须为不含凭据、查询参数和片段的 HTTP/HTTPS URL")
    return value


class FollowOptions(BaseModel):
    account: str
    media_only: bool = False
    replies: bool = False
    reposts: bool = False

    @field_validator("account")
    @classmethod
    def account_name(cls, value: str) -> str:
        return normalize_account(value)


class TwitterConfig(BaseModel):
    twitter_enabled: bool = False
    twitter_nitter_instances: list[str] = Field(default_factory=list)
    twitter_proxy: str = ""
    twitter_timeout: float = Field(default=15, ge=1, le=60)
    twitter_poll_interval: int = Field(default=600, ge=60, le=86400)
    twitter_concurrency: int = Field(default=2, ge=1, le=8)
    twitter_group_ids: list[str] = Field(default_factory=list)
    twitter_push_bot_id: str = ""
    twitter_follows: list[FollowOptions] = Field(default_factory=list)
    twitter_group_follows: dict[str, list[FollowOptions]] = Field(default_factory=dict)
    twitter_translation_provider: str = "model"
    twitter_model_base_url: str = ""
    twitter_model_name: str = ""
    twitter_model_api_key: str = ""
    twitter_libretranslate_url: str = ""
    twitter_libretranslate_api_key: str = ""
    twitter_translation_timeout: float = Field(default=30, ge=1, le=120)
    twitter_translation_limit: int = Field(default=4000, ge=100, le=20000)
    twitter_translation_cooldown: int = Field(default=30, ge=0, le=3600)
    twitter_card_body_limit: int = Field(default=600, ge=100, le=5000)

    @field_validator("twitter_nitter_instances", mode="before")
    @classmethod
    def instances(cls, value):
        return list(dict.fromkeys(service_url(item) for item in value if str(item).strip()))

    @field_validator("twitter_group_ids", mode="before")
    @classmethod
    def groups(cls, value):
        return list(dict.fromkeys(str(item) for item in value))

    @field_validator("twitter_push_bot_id", mode="before")
    @classmethod
    def bot_id(cls, value):
        return str(value) if value is not None else ""

    @field_validator("twitter_group_follows", mode="before")
    @classmethod
    def group_follows(cls, value):
        return {str(key): cls.expand_follows(items) for key, items in value.items()}

    @field_validator("twitter_follows", mode="before")
    @classmethod
    def expand_follows(cls, value):
        return [{"account": item} if isinstance(item, str) else item for item in value]

    @field_validator("twitter_model_base_url", "twitter_libretranslate_url")
    @classmethod
    def urls(cls, value):
        return service_url(value)

    @field_validator("twitter_translation_provider")
    @classmethod
    def provider(cls, value):
        if value not in {"model", "libretranslate"}:
            raise ValueError("翻译服务须为 model 或 libretranslate")
        return value
