from __future__ import annotations


def test_moyu_nested_data_is_normalized() -> None:
    from src.nonebot_plugins.liteyuki_60s.cards import card_view

    view = card_view(
        "moyu",
        {
            "date": {
                "gregorian": "2026-09-09",
                "weekday": "星期三",
                "lunar": {"yearGanZhi": "丙午", "zodiac": "马", "monthCN": "七月", "dayCN": "廿八"},
            },
            "today": {"isWorkday": True},
            "progress": {
                "week": {"passed": 3, "total": 7, "percentage": 43},
                "month": {"passed": 9, "total": 30, "percentage": 30},
                "year": {"passed": 252, "total": 365, "percentage": 69},
            },
            "nextWeekend": {"daysUntil": 3},
            "nextHoliday": {"name": "国庆节", "until": 22},
            "moyuQuote": "适度摸鱼。",
        },
    )
    assert view["variant"] == "moyu"
    assert view["date"] == "2026-09-09 星期三"
    assert {item["label"]: item["value"] for item in view["facts"]}["农历"] == "丙午 马 七月 廿八"
    assert [item["value"] for item in view["progress"]] == ["43%", "30%", "69%"]
    assert "{'gregorian'" not in str(view)


def test_it_card_has_titles_only() -> None:
    from src.nonebot_plugins.liteyuki_60s.cards import card_view

    view = card_view("it", {"news": [{"title": "IT 标题", "detail": "不应显示", "source": "来源"}]})
    assert view["items"] == [{"title": "IT 标题", "detail": "", "meta": ""}]


def test_hitokoto_and_luck_use_custom_variants() -> None:
    from src.nonebot_plugins.liteyuki_60s.cards import card_view

    assert card_view("hitokoto", {"hitokoto": "你好", "from": "作品"})["variant"] == "hitokoto"
    luck = card_view("luck", {"luck_desc": "大吉", "luck_rank": 95, "luck_tip": "放心前进"})
    assert luck["variant"] == "luck"
    assert luck["facts"][0]["value"] == "95"
