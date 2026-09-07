from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from src.utils.base.data import LiteModel


class Location(LiteModel):
    name: str = ""
    id: str = ""
    lat: str = ""
    lon: str = ""
    adm2: str = ""
    adm1: str = ""
    country: str = ""
    tz: str = ""
    utcOffset: str = ""
    isDst: str = ""
    type: str = ""
    rank: str = ""
    fxLink: str = ""


class CityLookup(LiteModel):
    code: str = ""
    location: list[Location] = Field(default_factory=list)
    refer: dict[str, Any] = Field(default_factory=dict)


def _nested(data: dict[str, Any], *path: str, default: Any = None) -> Any:
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return default if value is None else value


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _display(value: Any, digits: int = 1) -> str:
    number = round(_number(value), digits)
    return str(int(number)) if number.is_integer() else str(number)


def _value(data: dict[str, Any], *path: str, default: Any = "") -> Any:
    node = _nested(data, *path, default=default)
    return node.get("value", default) if isinstance(node, dict) else node


def _time(value: Any) -> str:
    text = str(value or "")
    if "T" not in text:
        return text
    return text.split("T", 1)[1][:5]


def _date(value: Any) -> str:
    text = str(value or "")
    return text.split("T", 1)[0]


def _attributions(*payloads: dict[str, Any], extra: str = "") -> list[str]:
    result: list[str] = []
    for payload in payloads:
        candidates = [
            _nested(payload, "metadata", "attributions", default=[]),
            _nested(payload, "metadata", "sources", default=[]),
            _nested(payload, "refer", "sources", default=[]),
            _nested(payload, "refer", "license", default=[]),
        ]
        for values in candidates:
            if isinstance(values, str):
                values = [values]
            if isinstance(values, list):
                for value in values:
                    text = str(value).strip()
                    if text and text not in result:
                        result.append(text)
    if extra and extra not in result:
        result.append(extra)
    return result


def _select_aqi(payload: dict[str, Any], country: str) -> dict[str, Any] | None:
    indexes = payload.get("indexes", payload.get("aqi", []))
    if not isinstance(indexes, list) or not indexes:
        return None

    normalized_country = country.strip().lower()
    if normalized_country in {"cn", "china", "中国", "中國", "中国大陆"}:
        for code in ("cn-mee", "cn-mee-1h"):
            if match := next((item for item in indexes if item.get("code") == code), None):
                return match

    if match := next(
        (item for item in indexes if item.get("defaultLocalAqi") is True), None
    ):
        return match
    if match := next(
        (
            item
            for item in indexes
            if item.get("code") not in {"qweather", "qaqi"}
        ),
        None,
    ):
        return match
    return indexes[0]


def _normalize_current(payload: dict[str, Any], imperial: bool) -> dict[str, Any]:
    if isinstance(payload.get("now"), dict):
        now = payload["now"]
        temperature = _number(now.get("temp"))
        feels_like = _number(now.get("feelsLike"))
        wind_speed_kmh = _number(now.get("windSpeed"))
        visibility_km = _number(now.get("vis"))
        precipitation_mm = _number(now.get("precip"))
        pressure_hpa = _number(now.get("pressure"))
        humidity = _number(now.get("humidity"))
        cloud_cover = _number(now.get("cloud"))
        observed_at = str(now.get("obsTime", ""))
        condition = {"text": now.get("text", ""), "code": now.get("icon", "999")}
        wind_degree = now.get("wind360", "")
        wind_compass = now.get("windDir", "")
        wind_scale = now.get("windScale", "")
    else:
        temperature = _number(_value(payload, "temperature"))
        feels_like = _number(_value(payload, "feelsLike"))
        wind_speed_kmh = _number(_value(payload, "wind", "speed")) * 3.6
        visibility_km = _number(_value(payload, "visibility")) / 1000
        precipitation_mm = _number(_value(payload, "precipitation", "amount"))
        pressure_hpa = _number(_value(payload, "pressure"))
        humidity = _number(payload.get("humidity")) * 100
        cloud_cover = _number(payload.get("cloudCover")) * 100
        observed_at = str(_nested(payload, "metadata", "updateTime", default=""))
        condition = payload.get("condition", {})
        wind_degree = _nested(payload, "wind", "direction", "degree", default="")
        wind_compass = _nested(payload, "wind", "direction", "compass", default="")
        wind_scale = _nested(payload, "wind", "scale", default="")

    if imperial:
        temperature = temperature * 9 / 5 + 32
        feels_like = feels_like * 9 / 5 + 32
        wind_speed = wind_speed_kmh * 0.621371
        visibility = visibility_km * 0.621371
        precipitation = precipitation_mm / 25.4
        pressure = pressure_hpa * 0.02953
    else:
        wind_speed = wind_speed_kmh
        visibility = visibility_km
        precipitation = precipitation_mm
        pressure = pressure_hpa

    return {
        "observed_at": observed_at,
        "temperature": _display(temperature),
        "feels_like": _display(feels_like),
        "icon": str(condition.get("code", "999")),
        "text": str(condition.get("text", "")),
        "wind_degree": str(wind_degree),
        "wind_compass": str(wind_compass),
        "wind_scale": str(wind_scale),
        "wind_speed": _display(wind_speed),
        "humidity": _display(humidity, 0),
        "precipitation": _display(precipitation, 2),
        "pressure": _display(pressure, 2 if imperial else 1),
        "visibility": _display(visibility, 1),
        "cloud_cover": _display(cloud_cover, 0),
    }


def _normalize_hourly(payload: dict[str, Any], imperial: bool) -> list[dict[str, str]]:
    source = payload.get("hours", payload.get("hourly", []))
    result: list[dict[str, str]] = []
    for item in source if isinstance(source, list) else []:
        if "fxTime" in item:
            temperature = _number(item.get("temp"))
            condition = {"code": item.get("icon", "999"), "text": item.get("text", "")}
            forecast_time = item.get("fxTime", "")
        else:
            temperature = _number(_value(item, "temperature"))
            condition = item.get("condition", {})
            forecast_time = item.get("forecastTime", "")
        if imperial:
            temperature = temperature * 9 / 5 + 32
        result.append(
            {
                "time": _time(forecast_time),
                "temperature": _display(temperature),
                "icon": str(condition.get("code", "999")),
                "text": str(condition.get("text", "")),
            }
        )
    return result


def _normalize_daily(payload: dict[str, Any], imperial: bool) -> list[dict[str, str]]:
    source = payload.get("days", payload.get("daily", []))
    result: list[dict[str, str]] = []
    for item in source if isinstance(source, list) else []:
        if "fxDate" in item:
            minimum = _number(item.get("tempMin"))
            maximum = _number(item.get("tempMax"))
            date = item.get("fxDate", "")
            icon_day = item.get("iconDay", "999")
            icon_night = item.get("iconNight", "999")
            text_day = item.get("textDay", "")
            sunrise = item.get("sunrise", "")
            sunset = item.get("sunset", "")
        else:
            minimum = _number(_value(item, "temperatureMin"))
            maximum = _number(_value(item, "temperatureMax"))
            date = item.get("forecastStartTime", "")
            daytime = item.get("daytime", {})
            nighttime = item.get("nighttime", {})
            icon_day = _nested(daytime, "condition", "code", default="999")
            icon_night = _nested(nighttime, "condition", "code", default=icon_day)
            text_day = _nested(daytime, "condition", "text", default="")
            sunrise = _nested(item, "astro", "sunrise", default="")
            sunset = _nested(item, "astro", "sunset", default="")
        if imperial:
            minimum = minimum * 9 / 5 + 32
            maximum = maximum * 9 / 5 + 32
        result.append(
            {
                "date": _date(date),
                "temp_min": _display(minimum),
                "temp_max": _display(maximum),
                "icon_day": str(icon_day),
                "icon_night": str(icon_night),
                "text_day": str(text_day),
                "sunrise": _time(sunrise),
                "sunset": _time(sunset),
            }
        )
    return result


def normalize_weather_data(
    location: Location,
    current: dict[str, Any],
    hourly: dict[str, Any],
    daily: dict[str, Any],
    air_quality: dict[str, Any],
    unit: str = "m",
    localization: dict[str, str] | None = None,
    extra_attribution: str = "",
    geo_reference: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Convert QWeather v1 (and legacy v7 fixtures) into the stable card model."""
    imperial = unit == "i"
    current_view = _normalize_current(current, imperial)
    daily_view = _normalize_daily(daily, imperial)
    selected_aqi = _select_aqi(air_quality, location.country)
    color = selected_aqi.get("color", {}) if selected_aqi else {}
    if isinstance(color, str):
        color = {"css": color}

    return {
        "params": {
            "unit": "i" if imperial else "m",
            "temperature_unit": "°F" if imperial else "°C",
            "wind_unit": "mph" if imperial else "km/h",
            "visibility_unit": "mi" if imperial else "km",
            "precipitation_unit": "in" if imperial else "mm",
            "pressure_unit": "inHg" if imperial else "hPa",
        },
        "location": {
            "name": location.name,
            "country": location.country,
            "adm1": location.adm1,
            "adm2": location.adm2,
            "lat": location.lat,
            "lon": location.lon,
        },
        "generated_at": generated_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "current": current_view,
        "hourly": _normalize_hourly(hourly, imperial),
        "daily": daily_view,
        "astronomy": {
            "sunrise": daily_view[0]["sunrise"] if daily_view else "",
            "sunset": daily_view[0]["sunset"] if daily_view else "",
        },
        "aqi": {
            "available": selected_aqi is not None,
            "value": str(
                selected_aqi.get("aqiDisplay", selected_aqi.get("valueDisplay", ""))
            )
            if selected_aqi
            else "",
            "category": str(selected_aqi.get("category", "")) if selected_aqi else "",
            "code": str(selected_aqi.get("code", "")) if selected_aqi else "",
            "color": color,
        },
        "localization": localization or {},
        "attributions": _attributions(
            {"refer": geo_reference or {}},
            current,
            hourly,
            daily,
            air_quality,
            extra=extra_attribution,
        ),
    }
