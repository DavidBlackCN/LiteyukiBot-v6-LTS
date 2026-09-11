"""Configuration for the built-in Bilibili service."""

from pydantic import BaseModel, Field


class BilibiliConfig(BaseModel):
    """Static settings; per-target subscriptions belong in the database."""

    bilibili_enabled: bool = True
    bilibili_cookie: str = ""
    bilibili_proxy: str = ""
    bilibili_api_timeout: float = Field(default=15.0, ge=1.0, le=60.0)
    bilibili_poll_interval: int = Field(default=30, ge=10, le=3600)
    bilibili_push_enabled: bool = True
    bilibili_link_parse_enabled: bool = True
    bilibili_push_dynamic: bool = True
    bilibili_push_video: bool = True
    bilibili_push_live: bool = True
    bilibili_render_scale: float = Field(default=1.5, ge=1.0, le=3.0)
