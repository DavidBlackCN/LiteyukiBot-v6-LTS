from __future__ import annotations

import asyncio

import nonebot
import pytest


def _init() -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_duckmo_maps_query_and_response_fixture() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.duckmo import DuckMoProvider

    client = _Client([{
        "errCode": "200", "success": True, "message": "成功", "data": [{
            "pid": 123, "uid": 456, "title": "title", "author": "artist",
            "width": 1200, "height": 1800, "aiType": 1,
            "tagsList": [{"tagName": "原神", "tagEn": "Genshin Impact"}],
            "urlsList": [
                {"urlSize": "regular", "url": "https://i.pixiv.re/regular.jpg"},
                {"urlSize": "original", "url": "https://i.pixiv.re/original.jpg"},
            ],
        }],
    }])
    query = ImageQuery(
        count=2, uid=[456], pid=[123], author="artist", size="original",
        exclude_ai=True, orientation="portrait", r18=True,
    )
    result = asyncio.run(DuckMoProvider(client, "https://api.mossia.top/duckMo").fetch(query))

    assert client.calls == [("POST", "https://api.mossia.top/duckMo", {"json": {
        "num": 2, "aiType": 1, "r18Type": 1, "sizeList": ["original"],
        "pid": [123], "uid": [456], "author": "artist", "imageSizeType": 2,
    }})]
    assert result[0].image_url.endswith("original.jpg")
    assert result[0].pid == 123 and result[0].uid == 456
    assert result[0].tags == ["原神"] and result[0].is_adult is True


def test_duckmo_falls_back_to_available_size() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.duckmo import DuckMoProvider

    client = _Client([{"success": True, "data": [{
        "pid": 1, "urlsList": [{"urlSize": "original", "url": "https://image/original.jpg"}],
    }]}])
    result = asyncio.run(DuckMoProvider(client, "https://api.example/duckMo").fetch(
        ImageQuery(count=1, size="regular")))
    assert result[0].image_url.endswith("original.jpg")


def test_duckmo_omits_ai_type_when_filter_is_disabled() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.duckmo import DuckMoProvider

    response = {"success": True, "data": [{
        "pid": 1, "urlsList": [{"urlSize": "regular", "url": "https://image/a.jpg"}],
    }]}
    filtered = _Client([response])
    asyncio.run(DuckMoProvider(filtered, "https://api.example/duckMo").fetch(
        ImageQuery(count=1, exclude_ai=True),
    ))
    assert filtered.calls[0][2]["json"]["aiType"] == 1

    unrestricted = _Client([response])
    asyncio.run(DuckMoProvider(unrestricted, "https://api.example/duckMo").fetch(
        ImageQuery(count=1, exclude_ai=False),
    ))
    assert "aiType" not in unrestricted.calls[0][2]["json"]


def test_duckmo_x_loops_single_result_endpoint() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.duckmo_x import DuckMoXProvider

    client = _Client([
        {"success": True, "data": [{"url": "https://x.com/a/status/1", "pictureUrl": "https://pbs/1.jpg"}]},
        {"success": True, "data": [{"url": "https://x.com/b/status/2", "pictureUrl": "https://pbs/2.jpg"}]},
    ])
    result = asyncio.run(DuckMoXProvider(client, "https://api.example/duckMo/x").fetch(
        ImageQuery(count=2, provider="duckmo_x")))
    assert len(client.calls) == 2
    assert [item.source_url for item in result] == ["https://x.com/a/status/1", "https://x.com/b/status/2"]
    assert result[0].fallback_image_urls == ["https://rand-x.mossia.top/"]


def test_duckmo_x_is_explicit_only_by_default() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery, UnsupportedQueryError
    from src.nonebot_plugins.liteyuki_setu.providers.duckmo_x import DuckMoXProvider
    from src.nonebot_plugins.liteyuki_setu.service import choose_providers

    provider = DuckMoXProvider(_Client([]), "https://api.example/duckMo/x")
    config = SetuConfig(
        setu_provider_order=["duckmo_x"], setu_provider_weights={"duckmo_x": 1},
    )
    with pytest.raises(UnsupportedQueryError):
        choose_providers(ImageQuery(), config, {"duckmo_x": provider})
    assert choose_providers(
        ImageQuery(provider="duckmo_x"), config, {"duckmo_x": provider},
    ) == [provider]

    enabled = config.model_copy(update={"setu_duckmo_x_random_pool_enabled": True})
    assert choose_providers(ImageQuery(), enabled, {"duckmo_x": provider}) == [provider]
