from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SixtyApiConfig(BaseModel):
    sixty_api_base_url: str = "https://60s.viki.moe"
    sixty_api_timeout: float = Field(default=10, gt=0, le=60)
    sixty_api_timezone: str = "Asia/Shanghai"
    sixty_api_group_mode: Literal["whitelist", "blacklist"] = "whitelist"
    sixty_api_group_ids: list[int] = Field(default_factory=list)
    sixty_api_push_bot_id: str = ""

    sixty_api_world_enabled: bool = True
    sixty_api_ai_enabled: bool = True
    sixty_api_history_enabled: bool = True
    sixty_api_it_enabled: bool = True
    sixty_api_moyu_enabled: bool = True
    sixty_api_hitokoto_enabled: bool = True
    sixty_api_luck_enabled: bool = True
    sixty_api_fabing_enabled: bool = True
    sixty_api_fabing_default_name: str = ""
    sixty_api_kfc_enabled: bool = True
    sixty_api_dad_joke_enabled: bool = True

    sixty_api_world_push_enabled: bool = False
    sixty_api_world_push_time: str = "08:30"
    sixty_api_ai_push_enabled: bool = False
    sixty_api_ai_push_time: str = "22:30"
    sixty_api_history_push_enabled: bool = False
    sixty_api_history_push_time: str = "09:00"
    sixty_api_it_push_enabled: bool = False
    sixty_api_it_push_time: str = "12:00"
    sixty_api_moyu_push_enabled: bool = False
    sixty_api_moyu_push_time: str = "09:10"
    sixty_api_kfc_push_enabled: bool = False
    sixty_api_kfc_push_time: str = "17:30"

    sixty_api_luck_daily_limit: int = Field(default=1, ge=0, le=100)

    sixty_api_fabing_random_push_enabled: bool = False
    sixty_api_fabing_random_min_interval_minutes: int = Field(default=180, ge=1)
    sixty_api_fabing_random_max_interval_minutes: int = Field(default=360, ge=1)
    sixty_api_fabing_random_start: str = "08:00"
    sixty_api_fabing_random_end: str = "22:00"
    sixty_api_dad_joke_random_push_enabled: bool = False
    sixty_api_dad_joke_random_min_interval_minutes: int = Field(default=180, ge=1)
    sixty_api_dad_joke_random_max_interval_minutes: int = Field(default=360, ge=1)
    sixty_api_dad_joke_random_start: str = "08:00"
    sixty_api_dad_joke_random_end: str = "22:00"

    @field_validator("sixty_api_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        from urllib.parse import urlparse

        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("sixty_api_base_url 必须是 HTTP/HTTPS URL")
        return value
