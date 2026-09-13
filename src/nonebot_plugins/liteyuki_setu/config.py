from __future__ import annotations

import warnings
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .providers.registry import provider_names


class SetuConfig(BaseModel):
    setu_private_enabled: bool = True
    setu_private_r18_enabled: bool = False
    setu_private_r18_user_ids: list[int] = Field(default_factory=list)
    setu_r18_max_count: int = Field(default=1, ge=1, le=5)
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
    setu_api_timeout: float | None = Field(default=None, ge=1, le=60)
    setu_image_timeout: float | None = Field(default=None, ge=1, le=120)
    setu_image_candidate_timeout: float = Field(default=8, ge=1, le=60)
    setu_image_candidate_retries: int = Field(default=0, ge=0, le=5)
    # Legacy shared timeout used only when a new timeout is not configured.
    setu_request_timeout: float = Field(default=15, ge=1, le=60)
    setu_request_retries: int = Field(default=2, ge=0, le=5)
    setu_group_mode: Literal["whitelist", "blacklist"] = "whitelist"
    setu_enabled_groups: list[int] = Field(default_factory=list)
    setu_provider_order: list[str] = Field(default_factory=lambda: [
        "lolicon", "random_mage", "duckmo", "duckmo_x", "mirlkoi", "liemoe",
        "waifuim",
    ])
    setu_provider_weights: dict[str, int] = Field(default_factory=lambda: {
        "lolicon": 2, "random_mage": 2, "duckmo": 2, "mirlkoi": 2, "liemoe": 3,
        "duckmo_x": 1, "waifuim": 1,
    })
    setu_default_provider: str = "auto"
    setu_pixiv_proxy: str = "i.pximg.net"
    setu_api_http_proxy: str = ""
    setu_image_http_proxy: str = ""
    setu_lolicon_api_http_proxy: str = ""
    setu_lolicon_image_http_proxy: str = ""
    setu_show_metadata: bool = True
    setu_superuser_bypass_cooldown: bool = True
    setu_download_concurrency: int = Field(default=3, ge=1, le=5)
    setu_provider_failure_threshold: int = Field(default=3, ge=1, le=10)
    setu_provider_cooldown_seconds: int = Field(default=120, ge=1, le=3600)
    setu_recent_dedup_enabled: bool = True
    setu_recent_dedup_hours: int = Field(default=24, ge=1, le=24 * 30)
    setu_recent_dedup_max_entries: int = Field(default=500, ge=1, le=10000)
    setu_recent_dedup_refill_attempts: int = Field(default=5, ge=0, le=20)

    setu_lolicon_enabled: bool = True
    setu_lolicon_api_url: str = "https://api.lolicon.app/setu/v2"
    setu_mirlkoi_enabled: bool = True
    setu_mirlkoi_base_url: str = "https://api.cnmiw.com"
    setu_mirlkoi_endpoint: str = "/api.php"
    setu_mirlkoi_sfw_sort: str = "CDNcat"
    setu_mirlkoi_r18_sort: str = "CDNsetu"
    setu_mirlkoi_random_sort: str = "CDNiw233"
    setu_mirlkoi_portrait_sort: str = "CDNmp"
    setu_mirlkoi_landscape_sort: str = "CDNpc"
    setu_duckmo_enabled: bool = True
    setu_duckmo_base_url: str = "https://api.mossia.top/duckMo"
    setu_duckmo_x_enabled: bool = True
    setu_duckmo_x_url: str = "https://api.mossia.top/duckMo/x"
    setu_duckmo_x_render_url: str = "https://rand-x.mossia.top/"
    setu_duckmo_x_random_pool_enabled: bool = False
    setu_random_mage_enabled: bool = True
    setu_random_mage_base_url: str = "https://i.mukyu.ru"
    setu_random_mage_api_key: str = ""
    setu_liemoe_enabled: bool = True
    setu_liemoe_base_url: str = "https://imgapi.lie.moe"
    setu_waifuim_enabled: bool = True
    setu_waifuim_base_url: str = "https://api.waifu.im"
    setu_waifuim_api_key: str = ""

    @field_validator(
        "setu_lolicon_api_url", "setu_mirlkoi_base_url", "setu_duckmo_base_url",
        "setu_duckmo_x_url", "setu_duckmo_x_render_url", "setu_random_mage_base_url",
        "setu_liemoe_base_url",
        "setu_waifuim_base_url",
    )
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

    @field_validator(
        "setu_api_http_proxy", "setu_image_http_proxy",
        "setu_lolicon_api_http_proxy", "setu_lolicon_image_http_proxy",
    )
    @classmethod
    def validate_http_proxy(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("出站代理必须是 HTTP/HTTPS URL")
        return value

    @field_validator(
        "setu_mirlkoi_sfw_sort", "setu_mirlkoi_r18_sort", "setu_mirlkoi_random_sort",
        "setu_mirlkoi_portrait_sort", "setu_mirlkoi_landscape_sort",
    )
    @classmethod
    def validate_mirlkoi_sort(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("MirlKoi 分类不能为空")
        return value

    @model_validator(mode="after")
    def normalize_counts(self) -> "SetuConfig":
        if self.setu_default_count > self.setu_max_count:
            self.setu_default_count = self.setu_max_count
        known = provider_names()
        order = [item.strip().lower() for item in self.setu_provider_order if item.strip()]
        unknown_order = [item for item in order if item not in known]
        if unknown_order:
            warnings.warn(f"忽略未知图片源顺序项: {', '.join(unknown_order)}", stacklevel=2)
        self.setu_provider_order = list(dict.fromkeys(item for item in order if item in known))
        self.setu_default_provider = self.setu_default_provider.strip().lower()
        if self.setu_default_provider not in provider_names(include_auto=True):
            raise ValueError("setu_default_provider 不受支持")
        weights: dict[str, int] = {}
        for raw_name, value in self.setu_provider_weights.items():
            name = raw_name.strip().lower()
            if name not in known:
                warnings.warn(f"忽略未知图片源权重: {raw_name}", stacklevel=2)
                continue
            if value < 0:
                warnings.warn(f"图片源 {name} 的负权重已按 0 处理", stacklevel=2)
            weights[name] = max(0, value)
        self.setu_provider_weights = weights
        return self
