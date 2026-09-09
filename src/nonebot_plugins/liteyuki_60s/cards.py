from __future__ import annotations

from typing import Any

from src.utils.base.resource import get_path
from src.utils.message.card_background import get_card_background
from src.utils.message.html_tool import template2image_element

from .client import SixtyApiError
from .service import TITLES, _list_items


def _text(value: Any, limit: int = 360) -> str:
    return str(value or "").strip()[:limit]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _progress(label: str, value: Any) -> dict[str, str] | None:
    item = _mapping(value)
    percentage = item.get("percentage")
    if percentage is None:
        return None
    return {
        "label": label,
        "value": f"{percentage}%",
        "detail": f"已过 {item.get('passed', '-')} / {item.get('total', '-')}",
        "percentage": str(max(0, min(100, int(percentage)))),
    }


def _moyu_view(value: dict[str, Any]) -> dict[str, Any]:
    date = _mapping(value.get("date"))
    lunar = _mapping(date.get("lunar"))
    today = _mapping(value.get("today"))
    next_weekend = _mapping(value.get("nextWeekend"))
    next_holiday = _mapping(value.get("nextHoliday"))
    countdown = _mapping(value.get("countdown"))
    holiday_name = _text(today.get("holidayName"))
    if holiday_name:
        today_text = holiday_name
    elif today.get("isHoliday"):
        today_text = "节假日"
    elif today.get("isWeekend"):
        today_text = "周末"
    elif today.get("isWorkday"):
        today_text = "工作日"
    else:
        today_text = "普通日"
    lunar_text = " ".join(filter(None, (_text(lunar.get("yearGanZhi")), _text(lunar.get("zodiac")), _text(lunar.get("monthCN")), _text(lunar.get("dayCN")))))
    facts = [
        {"label": "农历", "value": lunar_text},
        {"label": "今日", "value": today_text},
        {"label": "距周末", "value": f"{next_weekend.get('daysUntil')} 天" if next_weekend.get("daysUntil") is not None else "-"},
        {"label": "下个假期", "value": f"{_text(next_holiday.get('name'))} {next_holiday.get('until')} 天后" if next_holiday else "暂无"},
    ]
    progress = [item for item in (
        _progress("本周进度", _mapping(value.get("progress")).get("week")),
        _progress("本月进度", _mapping(value.get("progress")).get("month")),
        _progress("今年进度", _mapping(value.get("progress")).get("year")),
    ) if item]
    if countdown.get("toFriday") is not None:
        facts.append({"label": "距周五", "value": f"{countdown['toFriday']} 天"})
    return {
        "variant": "moyu",
        "title": TITLES["moyu"],
        "date": " ".join(filter(None, (_text(date.get("gregorian")), _text(date.get("weekday"))))),
        "headline": "今日也请适度摸鱼",
        "quote": _text(value.get("moyuQuote"), 600),
        "facts": facts,
        "progress": progress,
        "items": [],
    }


def card_view(feature: str, data: Any) -> dict[str, Any]:
    value = _mapping(data)
    view: dict[str, Any] = {
        "variant": "news",
        "title": TITLES[feature],
        "date": _text(value.get("date")),
        "headline": "",
        "items": [],
        "facts": [],
        "progress": [],
        "quote": "",
    }
    if feature == "moyu":
        return _moyu_view(value)
    if feature == "hitokoto":
        view.update({
            "variant": "hitokoto",
            "headline": _text(value.get("from") or value.get("from_who")),
            "quote": _text(value.get("hitokoto") if isinstance(data, dict) else data, 600),
        })
    elif feature == "luck":
        view.update({
            "variant": "luck",
            "headline": _text(value.get("luck_desc")),
            "facts": [
                {"label": "运势指数", "value": _text(value.get("luck_rank"))},
                {"label": "今日建议", "value": _text(value.get("luck_tip"), 180)},
            ],
        })
    else:
        if feature == "world":
            view["quote"] = _text(value.get("tip"), 500)
        for item in _list_items(data)[:20]:
            view["items"].append({
                "title": _text(item.get("title") or item.get("name") or item.get("description") or "资讯", 140),
                "detail": "" if feature == "it" else _text(item.get("detail") or item.get("description") or item.get("content"), 360),
                "meta": "" if feature == "it" else _text(item.get("source") or item.get("year") or item.get("event_type"), 80),
            })
    return view


async def render_card(feature: str, data: Any) -> bytes:
    template = get_path("templates/sixty_card.html", abs_path=True)
    if not template:
        raise SixtyApiError("60s 卡片资源尚未加载，请执行 rpm reload")
    view = card_view(feature, data)
    view["background"] = await get_card_background()
    try:
        return await template2image_element(
            template,
            {"data": view},
            "body",
            wait_for="window.sixtyCardReady === true",
            wait_timeout=5000,
        )
    except Exception as exc:
        raise SixtyApiError("图片生成失败") from exc