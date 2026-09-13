from __future__ import annotations

import asyncio

import nonebot


def _init() -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()


class _Client:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def test_random_mage_uses_feed_filters_and_converts_metadata() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.random_mage import RandomMageProvider

    client = _Client({"ok": True, "data": {"items": [{
        "image": {
            "id": "10", "illust_id": "123", "width": 1200, "height": 1800,
            "x_restrict": 0, "ai_type": 0, "title": "title",
            "user": {"id": "456", "name": "artist"},
        },
        "tags": ["原神", "甘雨"],
        "urls": {"proxy": "https://proxy.example/image.jpg", "local": "/i/10.jpg"},
    }], "count": 1}})
    query = ImageQuery(
        count=3, tags=["原神", "甘雨"], uid=[456], pid=[123],
        exclude_ai=True, orientation="portrait",
    )
    result = asyncio.run(RandomMageProvider(
        client, "https://i.mukyu.ru", "secret",
    ).fetch(query))

    assert client.calls == [("GET", "https://i.mukyu.ru/feed", {
        "params": [
            ("limit", 3), ("r18", 0), ("r18_strict", 1), ("ai_type", "0"),
            ("included_tags", "原神"), ("included_tags", "甘雨"),
            ("user_id", 456), ("illust_id", 123), ("orientation", "portrait"),
        ],
        "headers": {"X-API-Key": "secret"},
    })]
    assert result[0].pid == "123" and result[0].uid == "456"
    assert result[0].author == "artist" and result[0].tags == ["原神", "甘雨"]
    assert result[0].is_adult is False


def test_random_mage_does_not_claim_free_keyword_or_multiple_ids() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.random_mage import RandomMageProvider

    provider = RandomMageProvider(_Client({}), "https://i.mukyu.ru")
    assert not provider.supports(ImageQuery(keyword="genshin"))
    assert not provider.supports(ImageQuery(uid=[1, 2]))
    assert not provider.supports(ImageQuery(pid=[1, 2]))


def test_liemoe_maps_safe_orientation_and_thumbnail(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers import liemoe

    async def no_wait():
        return None

    monkeypatch.setattr(liemoe._rate_limiter, "wait", no_wait)
    client = _Client({"pic": ["https://imghost.lie.moe/image.jpg"], "remain_num": 999})
    result = asyncio.run(liemoe.LieMoeProvider(client, "https://imgapi.lie.moe").fetch(
        ImageQuery(count=2, orientation="landscape", size="thumb")))

    assert client.calls == [("GET", "https://imgapi.lie.moe/random", {"params": {
        "sort": "pc", "type": "json", "num": 2, "thumbnail": "medium",
    }})]
    assert result[0].is_adult is False
