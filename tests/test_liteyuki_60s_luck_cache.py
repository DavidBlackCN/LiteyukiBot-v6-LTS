from __future__ import annotations


def test_luck_request_limit_returns_last_successful_card() -> None:
    from src.nonebot_plugins.liteyuki_60s.state import (
        LuckUsage,
        begin_luck_request,
        luck_db,
        record_luck_result,
    )

    user_id, date = "pytest-60s-cache-user", "2099-02-01"
    luck_db.delete(LuckUsage(), "user_id = ?", user_id)

    first = begin_luck_request(user_id, date, 1)
    assert first.should_fetch and first.cached_result is None
    record_luck_result(user_id, date, b"last-luck-card")

    repeated = begin_luck_request(user_id, date, 1)
    assert not repeated.should_fetch
    assert repeated.cached_result == b"last-luck-card"


def test_fabing_default_name_is_used_when_command_name_is_empty() -> None:
    from src.nonebot_plugins.liteyuki_60s.config import SixtyApiConfig

    config = SixtyApiConfig(sixty_api_fabing_default_name="小雪")
    assert config.sixty_api_fabing_default_name == "小雪"
