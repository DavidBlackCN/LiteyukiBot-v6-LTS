"""Komari plugin configuration."""

from functools import lru_cache

from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    komari_url: str = "http://127.0.0.1:25774"
    komari_username: str | None = None
    komari_password: str | None = None
    komari_storage_state_path: str | None = None
    komari_screenshot_width: int = 1920
    komari_screenshot_height: int = 1080
    komari_device_scale_factor: float = 1.0
    komari_screenshot_type: str = "jpeg"
    komari_screenshot_quality: int = 85
    komari_wait_selector: str = "body"
    komari_wait_timeout: int = 10000
    komari_wait_networkidle: bool = False
    komari_networkidle_timeout: int = 3000
    komari_ready_selector: str = ".km-node-card"
    komari_ready_min_count: int = 1
    komari_background_url: str | None = None
    komari_loading_text: str = "加载中"
    komari_render_delay_ms: int = 1000
    komari_group_allowlist: list[int] = []
    komari_cooldown_seconds: int = 30


@lru_cache(maxsize=1)
def get_config() -> Config:
    return get_plugin_config(Config)
