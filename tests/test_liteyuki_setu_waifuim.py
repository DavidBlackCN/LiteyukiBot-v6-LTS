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


def test_waifuim_maps_filters_and_current_v1_response() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.waifuim import WaifuImProvider

    client = _Client({"items": [{
        "id": 6758,
        "source": "https://www.pixiv.net/en/artworks/81300646",
        "artists": [{
            "id": 838, "name": "artist", "pixiv": "https://www.pixiv.net/users/544561",
        }],
        "isNsfw": True, "width": 1600, "height": 2088,
        "url": "https://cdn.waifu.im/6758.png",
        "tags": [{"name": "Waifu", "slug": "waifu"}],
    }]})
    query = ImageQuery(
        count=3, keyword="waifu", tags=["maid"], orientation="portrait", r18=True,
    )
    result = asyncio.run(WaifuImProvider(
        client, "https://api.waifu.im", "secret",
    ).fetch(query))

    assert client.calls == [("GET", "https://api.waifu.im/images", {
        "params": [
            ("IsNsfw", "True"), ("OrderBy", "Random"), ("PageSize", 3),
            ("IncludedTags", "maid"), ("IncludedTags", "waifu"),
            ("Orientation", "Portrait"),
        ],
        "headers": {"X-Api-Key": "secret"},
    })]
    assert result[0].pid == "81300646" and result[0].uid == "544561"
    assert result[0].author == "artist" and result[0].tags == ["waifu"]
    assert result[0].is_adult is True


def test_waifuim_does_not_claim_ai_or_size_filtering() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.waifuim import WaifuImProvider

    provider = WaifuImProvider(_Client({}), "https://api.waifu.im")
    assert not provider.supports(ImageQuery(
        exclude_ai=True, explicit_filters=frozenset({"exclude_ai"}),
    ))
    assert not provider.supports(ImageQuery(
        size="original", explicit_filters=frozenset({"size"}),
    ))
