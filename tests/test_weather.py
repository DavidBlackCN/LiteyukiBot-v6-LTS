from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_python(source: str) -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    assert result.returncode == 0, (
        f"subprocess failed with code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


BOOTSTRAP = """
import nonebot
import liteyuki.utils
from nonebot.adapters.onebot.v11 import Adapter

liteyuki.utils.IS_MAIN_PROCESS = False
from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)
starter._load_htmlrender_plugin()
starter._load_alconna_plugin()
plugin = nonebot.load_plugin("src.nonebot_plugins.liteyuki_weather")
assert plugin is not None
"""


def test_weather_plugin_commands_and_conservative_natural_trigger() -> None:
    _run_python(
        BOOTSTRAP
        + """
from src.nonebot_plugins.liteyuki_weather.qweather import (
    extract_weather_location,
    natural_weather,
    weather_command,
)

assert nonebot.get_plugin("liteyuki_weather") is plugin
assert weather_command.command.parse("weather 深圳").matched
assert weather_command.command.parse("天气 深圳").matched
assert weather_command.command.parse("weather 深圳").main_args["keywords"] == ("深圳",)
assert "/" in nonebot.get_driver().config.command_start
assert natural_weather.priority == 90
assert natural_weather.block is True

accepted = {
    "深圳天气": "深圳",
    "深圳今天天气": "深圳",
    "深圳天气怎么样": "深圳",
    "深圳天气如何": "深圳",
    "查一下深圳天气": "深圳",
    "看看深圳天气": "深圳",
    "广东 深圳天气": "广东 深圳",
}
for text, expected in accepted.items():
    assert extract_weather_location(text) == expected, text

for text in ("今天天气真好", "天气不错", "这天气太热了", "天气怎么这样", "今天天气如何"):
    assert extract_weather_location(text) is None, text
"""
    )


def test_weather_card_opts_into_public_background_and_waits_until_ready() -> None:
    _run_python(
        BOOTSTRAP
        + """
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.nonebot_plugins.liteyuki_weather import qweather
from src.nonebot_plugins.liteyuki_weather.qw_models import Location

class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def city_lookup(self, *args, **kwargs):
        return SimpleNamespace(
            code="200",
            location=[Location(name="深圳", lat="22.55", lon="114.05")],
            refer={},
        )

    async def weather_current(self, *args, **kwargs):
        return {}

    async def weather_hourly(self, *args, **kwargs):
        return {}

    async def weather_daily(self, *args, **kwargs):
        return {}

    async def air_quality_current(self, *args, **kwargs):
        return {}

async def main():
    qweather.get_config = lambda key, default="": {
        "weather_api_host": "demo.qweatherapi.com",
        "weather_key": "secret",
    }.get(key, default)
    qweather.get_user_lang = lambda _: SimpleNamespace(
        lang_code="zh-CN", get=lambda key, **kwargs: kwargs.get("default", key)
    )
    qweather.user_db = SimpleNamespace(
        where_one=lambda *args, **kwargs: SimpleNamespace(profile={})
    )
    qweather.QWeatherClient = FakeClient
    qweather.normalize_weather_data = lambda *args, **kwargs: {"location": {"name": "深圳"}}
    qweather.get_local_data = lambda _: {}
    qweather.get_path = lambda *args, **kwargs: "weather_now.html"
    qweather.get_card_background = AsyncMock(
        return_value={"image": "data:image/png;base64,cG5n", "mask": 0.35}
    )
    qweather.template2image_element = AsyncMock(return_value=b"png")

    result = await qweather.build_weather_card(SimpleNamespace(user_id=1), ["深圳"])
    assert result == b"png"
    qweather.get_card_background.assert_awaited_once_with()
    args = qweather.template2image_element.call_args
    assert args.args[1]["data"]["background"]["image"].startswith("data:image/png")
    assert args.args[2] == "body"
    assert args.kwargs["wait_for"] == "window.weatherCardReady === true"
    assert args.kwargs["wait_timeout"] == 5000

asyncio.run(main())
"""
    )


def test_qweather_v1_geo_weather_and_aqi_requests() -> None:
    _run_python(
        BOOTSTRAP
        + """
import asyncio
import httpx

from src.nonebot_plugins.liteyuki_weather.qw_api import QWeatherClient

requests = []

def handler(request: httpx.Request) -> httpx.Response:
    requests.append(request)
    path = request.url.path
    if path == "/geo/v2/city/lookup":
        return httpx.Response(200, json={
            "code": "200",
            "location": [{
                "name": "深圳", "id": "101280601", "lat": "22.55", "lon": "114.05",
                "adm2": "深圳", "adm1": "广东", "country": "中国"
            }],
            "refer": {"sources": ["https://developer.qweather.com/attribution.html"]},
        })
    if path.startswith("/weather/v1/current/"):
        return httpx.Response(200, json={"metadata": {"attributions": ["QWeather"]}, "condition": {"text": "晴", "code": "100"}, "temperature": {"value": 30, "unit": "°C"}})
    if path.startswith("/weather/v1/hourly/"):
        return httpx.Response(200, json={"metadata": {"attributions": ["QWeather"]}, "hours": []})
    if path.startswith("/weather/v1/daily/"):
        return httpx.Response(200, json={"metadata": {"attributions": ["QWeather"]}, "days": []})
    if path.startswith("/airquality/v1/current/"):
        return httpx.Response(200, json={"metadata": {"attributions": ["QWeather"]}, "indexes": []})
    raise AssertionError(path)

async def main():
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        async with QWeatherClient("demo.qweatherapi.com", "secret", http_client) as client:
            lookup = await client.city_lookup("深圳", adm="广东", lang="zh-CN")
            assert lookup.location[0].lat == "22.55"
            location = lookup.location[0]
            current = await client.weather_current(location)
            hourly = await client.weather_hourly(location)
            daily = await client.weather_daily(location)
            aqi = await client.air_quality_current(location)
            assert current["condition"]["code"] == "100"
            assert hourly["hours"] == []
            assert daily["days"] == []
            assert aqi["indexes"] == []

asyncio.run(main())

assert len(requests) == 5
assert all(request.headers["X-QW-Api-Key"] == "secret" for request in requests)
assert requests[0].url.params["location"] == "深圳"
assert requests[0].url.params["adm"] == "广东"
assert all("22.55/114.05" in str(request.url) for request in requests[1:])
"""
    )


def test_weather_v1_and_legacy_data_normalize_and_render() -> None:
    _run_python(
        BOOTSTRAP
        + """
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.nonebot_plugins.liteyuki_weather.qw_models import Location, normalize_weather_data

location = Location(name="深圳", lat="22.55", lon="114.05", adm1="广东", adm2="深圳", country="中国")
current = {
    "metadata": {"attributions": ["https://developer.qweather.com/attribution.html"]},
    "condition": {"text": "晴", "code": "100"},
    "temperature": {"value": 20, "unit": "°C"},
    "feelsLike": {"value": 21, "unit": "°C"},
    "humidity": 0.55,
    "wind": {"direction": {"degree": 90, "compass": "e"}, "speed": {"value": 2, "unit": "m/s"}, "scale": 2},
    "precipitation": {"amount": {"value": 1, "unit": "mm"}},
    "pressure": {"value": 1000, "unit": "hPa"},
    "visibility": {"value": 10000, "unit": "m"},
    "cloudCover": 0.2,
}
hourly = {"metadata": {"attributions": ["QWeather"]}, "hours": [{"forecastTime": "2026-01-01T10:00+08:00", "condition": {"text": "晴", "code": "100"}, "temperature": {"value": 22, "unit": "°C"}}]}
daily = {"metadata": {"attributions": ["QWeather"]}, "days": [{
    "forecastStartTime": "2026-01-01T00:00+08:00",
    "temperatureMin": {"value": 15, "unit": "°C"},
    "temperatureMax": {"value": 25, "unit": "°C"},
    "daytime": {"condition": {"text": "晴", "code": "100"}},
    "nighttime": {"condition": {"text": "多云", "code": "101"}},
    "astro": {"sunrise": "2026-01-01T06:00+08:00", "sunset": "2026-01-01T18:00+08:00"},
}]}
air = {"metadata": {"attributions": ["QWeather"]}, "indexes": [
    {"code": "qweather", "aqiDisplay": "20", "category": "Good", "color": {"red": 1, "green": 2, "blue": 3, "alpha": 1}},
    {"code": "cn-mee", "aqiDisplay": "42", "category": "优", "color": {"red": 0, "green": 228, "blue": 0, "alpha": 1}},
]}
view = normalize_weather_data(
    location,
    current,
    hourly,
    daily,
    air,
    geo_reference={"sources": ["Geo attribution"]},
    generated_at="2026-01-01T09:00:00+08:00",
)
assert view["current"]["humidity"] == "55"
assert view["current"]["wind_speed"] == "7.2"
assert view["current"]["visibility"] == "10"
assert view["daily"][0]["sunrise"] == "06:00"
assert view["aqi"]["code"] == "cn-mee"
assert "https://developer.qweather.com/attribution.html" in view["attributions"]
assert "Geo attribution" in view["attributions"]

imperial = normalize_weather_data(location, current, hourly, daily, air, unit="i")
assert imperial["current"]["temperature"] == "68"
assert imperial["params"]["temperature_unit"] == "°F"
assert imperial["params"]["wind_unit"] == "mph"

legacy = normalize_weather_data(
    location,
    {"now": {"obsTime": "2024-01-01T09:00+08:00", "temp": "20", "feelsLike": "21", "icon": "100", "text": "晴", "wind360": "90", "windDir": "东风", "windScale": "2", "windSpeed": "7", "humidity": "55", "precip": "0", "pressure": "1000", "vis": "10", "cloud": "20"}},
    {"hourly": [{"fxTime": "2024-01-01T10:00+08:00", "temp": "22", "icon": "100", "text": "晴"}]},
    {"daily": [{"fxDate": "2024-01-01", "tempMin": "15", "tempMax": "25", "iconDay": "100", "iconNight": "101", "textDay": "晴", "sunrise": "06:00", "sunset": "18:00"}]},
    {"aqi": [{"defaultLocalAqi": True, "valueDisplay": "42", "category": "优", "color": {"red": 0, "green": 228, "blue": 0, "alpha": 1}}]},
    generated_at="2024-01-01T09:00:00+08:00",
)
assert legacy["current"]["icon"] == "100"
assert legacy["daily"][0]["temp_max"] == "25"

template_dir = Path("src/resources/liteyuki_weather/templates")
environment = Environment(loader=FileSystemLoader(template_dir), autoescape=select_autoescape())
template = environment.get_template("weather_now.html")
for model in (view, legacy):
    html = template.render(data=model)
    assert "Liteyuki Weather" in html
    assert '"current"' in html
    assert model["location"]["name"] == "深圳"
    assert '"location"' in html

weather_html = (template_dir / "weather_now.html").read_text(encoding="utf-8")
weather_js = (template_dir / "js/weather_now.js").read_text(encoding="utf-8")
assert 'class="card-background-page"' in weather_html
assert 'id="card-background-image"' in weather_html
assert "card_background.js" in weather_html
assert "window.weatherCardReady = true" in weather_js
"""
    )


def test_missing_config_and_network_failures_are_controlled() -> None:
    _run_python(
        BOOTSTRAP
        + """
import asyncio
from types import SimpleNamespace

import httpx

from src.nonebot_plugins.liteyuki_weather import qweather
from src.nonebot_plugins.liteyuki_weather.qw_api import QWeatherClient, QWeatherConfigError, QWeatherError

event = SimpleNamespace(user_id=123)

async def main():
    qweather.get_config = lambda key, default="": ""
    try:
        await qweather.build_weather_card(event, ["深圳"])
    except qweather.WeatherUserError as error:
        assert "weather_api_host" in str(error)
    else:
        raise AssertionError("missing host was accepted")

    qweather.get_config = lambda key, default="": "demo.qweatherapi.com" if key == "weather_api_host" else ""
    try:
        await qweather.build_weather_card(event, ["深圳"])
    except qweather.WeatherUserError as error:
        assert "weather_key" in str(error) or "API" in str(error)
    else:
        raise AssertionError("missing key was accepted")

    def network_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(network_failure)) as http_client:
        async with QWeatherClient("demo.qweatherapi.com", "secret", http_client) as client:
            try:
                await client.city_lookup("深圳")
            except QWeatherError as error:
                assert "无法连接" in str(error)
            else:
                raise AssertionError("network error escaped conversion")

    async def failed_build(event, keywords):
        raise QWeatherError("offline")

    qweather.build_weather_card = failed_build
    try:
        await qweather.get_weather_now_card(None, event, ["深圳"])
    except qweather.WeatherUserError as error:
        assert "offline" in str(error)
    else:
        raise AssertionError("network error was not converted for the matcher")

    try:
        QWeatherClient("http://invalid.example", "secret")
    except QWeatherConfigError:
        pass
    else:
        raise AssertionError("non-HTTPS host was accepted")

asyncio.run(main())
"""
    )
