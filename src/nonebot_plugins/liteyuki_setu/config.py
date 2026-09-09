from __future__ import annotations

from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator


class SetuConfig(BaseModel):
    setu_private_enabled: bool = True
    setu_private_r18_enabled: bool = False
    setu_private_r18_user_ids: list[int] = Field(default_factory=list)
    setu_default_count: int = Field(default=3, ge=1, le=5)
    setu_max_count: int = Field(default=5, ge=1, le=5)
    setu_cooldown_seconds: int = Field(default=30, ge=0, le=3600)
    setu_send_interval_seconds: float = Field(default=1.0, ge=0, le=10)
    setu_auto_recall: bool = True
    setu_recall_seconds: int = Field(default=60, ge=5, le=600)
    setu_exclude_ai: bool = True
    setu_daily_image_limit_per_user: int = Field(default=0, ge=0, le=1000)
    setu_daily_limit_timezone: str = "Asia/Shanghai"
    setu_image_size: str = "regular"
    setu_image_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    setu_request_timeout: float = Field(default=15, ge=1, le=60)
    setu_request_retries: int = Field(default=2, ge=0, le=5)
    setu_enabled_groups: list[int] = Field(default_factory=list)
    setu_provider_order: list[str] = Field(default_factory=lambda: ["lolicon", "mirlkoi"])
    setu_default_provider: str = "auto"
    setu_pixiv_proxy: str = "i.pixiv.re"
    setu_show_metadata: bool = True
    setu_superuser_bypass_cooldown: bool = True
    setu_download_concurrency: int = Field(default=3, ge=1, le=5)
    setu_provider_failure_threshold: int = Field(default=3, ge=1, le=10)
    setu_provider_cooldown_seconds: int = Field(default=120, ge=1, le=3600)

    setu_lolicon_enabled: bool = True
    setu_lolicon_api_url: str = "https://api.lolicon.app/setu/v2"
    setu_mirlkoi_enabled: bool = True
    setu_mirlkoi_base_url: str = "https://api.cnmiw.com"
    setu_mirlkoi_endpoint: str = "/api.php"

    @field_validator("setu_lolicon_api_url", "setu_mirlkoi_base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("图片源地址必须是 HTTP/HTTPS URL")
        return value

    @field_validator("setu_daily_limit_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError("setu_daily_limit_timezone 必须是有效时区") from exc
        return value

    @field_validator("setu_image_size")
    @classmethod
    def validate_size(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"original", "regular", "small", "thumb", "mini"}:
            raise ValueError("setu_image_size 不受支持")
        return value

    @model_validator(mode="after")
    def normalize_counts(self) -> "SetuConfig":
        if self.setu_default_count > self.setu_max_count:
            self.setu_default_count = self.setu_max_count
        self.setu_provider_order = [item.strip().lower() for item in self.setu_provider_order if item.strip()]
        if self.setu_default_provider not in {"auto", "lolicon", "mirlkoi"}:
            raise ValueError("setu_default_provider 不受支持")
        return self