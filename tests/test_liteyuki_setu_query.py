from __future__ import annotations

import asyncio

import nonebot


def _init() -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()


class _Client:
    def __init__(self) -> None:
        self.payload = None

    async def request_json(self, method, url, **kwargs):
        self.payload = (method, url, kwargs["json"])
        return {"data": [{
            "pid": 1, "uid": 2, "r18": False, "tags": ["萝莉", "原神"],
            "urls": {"regular": "https://image.example/test.jpg"},
        }]}


def test_quantity_suffix_is_not_sent_as_a_keyword() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.parser import parse_query

    query = parse_query("3张 萝莉")
    assert query.count == 3
    assert query.keyword == "萝莉"


def test_lolicon_preserves_keyword_tag_and_uid_filters() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.parser import parse_query
    from src.nonebot_plugins.liteyuki_setu.providers.lolicon import LoliconProvider

    query = parse_query("2张 原神 -t 萝莉 -t 甘雨 --uid 10001", default_exclude_ai=False)
    client = _Client()
    results = asyncio.run(LoliconProvider(client, "https://api.example/setu", "").fetch(query))

    assert results[0].tags == ["萝莉", "原神"]
    assert client.payload == ("POST", "https://api.example/setu", {
        "r18": 0, "num": 2, "size": ["regular"], "excludeAI": 0,
        "keyword": "原神", "tag": ["萝莉", "甘雨"], "uid": [10001],
    })
