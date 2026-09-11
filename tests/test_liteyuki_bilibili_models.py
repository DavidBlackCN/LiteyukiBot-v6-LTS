from datetime import datetime

import pytest
from pydantic import ValidationError

from src.nonebot_plugins.liteyuki_bilibili.config import BilibiliConfig
from src.nonebot_plugins.liteyuki_bilibili.models import BilibiliEvent


def test_config_has_safe_bilibili_defaults() -> None:
    config = BilibiliConfig()

    assert config.bilibili_enabled is True
    assert config.bilibili_cookie == ""
    assert config.bilibili_poll_interval == 30
    assert config.bilibili_render_scale == 1.5


def test_config_rejects_unsafe_timeout_and_poll_interval() -> None:
    with pytest.raises(ValidationError):
        BilibiliConfig(bilibili_api_timeout=0)
    with pytest.raises(ValidationError):
        BilibiliConfig(bilibili_poll_interval=9)


def test_event_is_a_normalized_cross_feature_view_model() -> None:
    event = BilibiliEvent(
        kind="video",
        uid="123",
        event_id="BV1xx411c7mD",
        title="测试视频",
        timestamp=datetime(2026, 1, 1),
        cover_urls=["https://i0.hdslb.com/cover.jpg"],
        metrics={"play": 42},
    )

    assert event.kind == "video"
    assert event.metrics == {"play": 42}
