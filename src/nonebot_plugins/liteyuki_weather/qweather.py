from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable

import nonebot
from nonebot import on_regex, require
from nonebot.internal.matcher import Matcher

from src.utils import event as event_utils
from src.utils.base.config import get_config
from src.utils.base.data_manager import User, user_db
from src.utils.base.language import Language, get_user_lang
from src.utils.base.ly_typing import T_MessageEvent
from src.utils.base.resource import get_path
from src.utils.message.html_tool import template2image

from .qw_api import QWeatherClient, QWeatherError, get_local_data, get_qw_lang
from .qw_models import normalize_weather_data

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Alconna, Args, Arparma, MultiVar, UniMessage, on_alconna


WEATHER_QUERY_PATTERN = re.compile(
    r"^(?:(?:查一下|查查|帮我查(?:一下)?|看看)\s*)?"
    r"(?!今天(?:天气|$)|明天(?:天气|$)|这天气|天气)"
    r"(?P<location>[\u4e00-\u9fffA-Za-z0-9·\-]+(?:\s+[\u4e00-\u9fffA-Za-z0-9·\-]+){0,3}?)"
    r"(?:天气|weather)(?:怎么样|如何|情况)?[？?]?$",
    re.IGNORECASE,
)


class WeatherUserError(RuntimeError):
    pass


def extract_weather_location(text: str) -> str | None:
    match = WEATHER_QUERY_PATTERN.fullmatch(str(text or "").strip())
    if not match:
        return None
    location = " ".join(match.group("location").split())
    if location.endswith("今天"):
        location = location[:-2].strip()
    if location in {"今天", "明天", "现在", "这", "这个"}:
        return None
    return location or None


def normalize_query_parts(keywords: str | Iterable[str] | None) -> list[str]:
    if keywords is None:
        return []
    if isinstance(keywords, str):
        return [part for part in keywords.split() if part]
    return [str(part).strip() for part in keywords if str(part).strip()]


def _message(ulang: Language, key: str, default: str, **kwargs: object) -> str:
    message = str(ulang.get(key, default=default, **kwargs))
    try:
        return message.format(**kwargs)
    except (IndexError, KeyError, ValueError):
        return message


async def build_weather_card(
    event: T_MessageEvent, keywords: str | Iterable[str] | None
) -> bytes:
    user_id = str(event_utils.get_user_id(event))
    ulang = get_user_lang(user_id)
    api_host = str(get_config("weather_api_host", "") or "").strip()
    api_key = str(get_config("weather_key", "") or "").strip()
    if not api_host:
        raise WeatherUserError(
            _message(
                ulang,
                "weather.no_host",
                "未设置和风天气 API Host，请配置 weather_api_host",
            )
        )
    if not api_key:
        raise WeatherUserError(
            _message(
                ulang,
                "weather.no_key",
                "未设置和风天气 API Key，请配置 weather_key",
            )
        )

    user: User = user_db.where_one(
        User(), "user_id = ?", user_id, default=User(user_id=user_id)
    )
    unit = "i" if user.profile.get("unit") == "i" else "m"
    parts = normalize_query_parts(keywords)
    if parts:
        adm = " ".join(parts[:-1]) if len(parts) > 1 else ""
        city = parts[-1]
        city_name = " ".join(parts)
    else:
        stored_location = str(user.profile.get("location", "") or "").strip()
        if not stored_location:
            raise WeatherUserError(
                _message(
                    ulang,
                    "weather.no_location",
                    "请指定城市，或先在个人资料中设置默认 location",
                )
            )
        adm = ""
        city = stored_location
        city_name = stored_location

    qw_lang = get_qw_lang(ulang.lang_code)
    async with QWeatherClient(api_host, api_key) as client:
        city_info = await client.city_lookup(city, adm=adm, lang=qw_lang)
        if city_info.code != "200" or not city_info.location:
            raise WeatherUserError(
                _message(
                    ulang,
                    "weather.city_not_found",
                    "未找到城市 {CITY}",
                    CITY=city_name,
                )
            )
        location = city_info.location[0]
        current, hourly, daily = await asyncio.gather(
            client.weather_current(location, lang=qw_lang),
            client.weather_hourly(location, lang=qw_lang),
            client.weather_daily(location, lang=qw_lang),
        )
        try:
            air_quality = await client.air_quality_current(location, lang=qw_lang)
        except QWeatherError as e:
            nonebot.logger.warning(f"获取 {city_name} 空气质量失败，天气卡将不显示 AQI：{e}")
            air_quality = {}

    view_model = normalize_weather_data(
        location,
        current,
        hourly,
        daily,
        air_quality,
        unit=unit,
        localization=get_local_data(ulang.lang_code),
        extra_attribution=str(get_config("weather_attr", "") or "").strip(),
        geo_reference=city_info.refer,
    )
    template = get_path("templates/weather_now.html", abs_path=True)
    if not template:
        raise WeatherUserError(
            _message(ulang, "weather.no_template", "天气卡资源尚未加载，请执行 rpm reload")
        )
    return await template2image(template=template, templates={"data": view_model})


async def get_weather_now_card(
    matcher: Matcher,
    event: T_MessageEvent,
    keywords: str | Iterable[str] | None,
) -> bytes:
    try:
        return await build_weather_card(event, keywords)
    except WeatherUserError:
        raise
    except QWeatherError as e:
        ulang = get_user_lang(str(event_utils.get_user_id(event)))
        raise WeatherUserError(
            _message(
                ulang,
                "weather.request_failed",
                "天气服务暂时不可用：{ERROR}",
                ERROR=str(e),
            )
        ) from e
    except Exception as e:
        nonebot.logger.exception(f"生成天气卡失败：{e}")
        ulang = get_user_lang(str(event_utils.get_user_id(event)))
        raise WeatherUserError(
            _message(
                ulang,
                "weather.request_failed",
                "天气服务暂时不可用，请稍后重试",
            )
        ) from e


weather_command = on_alconna(
    aliases={"天气"},
    command=Alconna("weather", Args["keywords", MultiVar(str), []]),
)


@weather_command.handle()
async def _(result: Arparma, event: T_MessageEvent, matcher: Matcher):
    try:
        image = await get_weather_now_card(
            matcher, event, result.main_args.get("keywords")
        )
    except WeatherUserError as e:
        await matcher.finish(str(e))
        return
    await matcher.finish(UniMessage.image(raw=image))


natural_weather = on_regex(
    WEATHER_QUERY_PATTERN.pattern,
    flags=re.IGNORECASE,
    priority=90,
    block=True,
)


@natural_weather.handle()
async def _(event: T_MessageEvent, matcher: Matcher):
    location = extract_weather_location(event.get_plaintext())
    if location is None:
        return
    try:
        image = await get_weather_now_card(matcher, event, location)
    except WeatherUserError as e:
        await matcher.finish(str(e))
        return
    await matcher.finish(UniMessage.image(raw=image))
