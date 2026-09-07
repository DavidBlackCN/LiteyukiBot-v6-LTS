from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from src.utils.base.language import Language

from .qw_models import CityLookup, Location


HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class QWeatherError(RuntimeError):
    pass


class QWeatherConfigError(QWeatherError):
    pass


class QWeatherDataError(QWeatherError):
    pass


def normalize_api_host(host: str) -> str:
    value = str(host or "").strip().rstrip("/")
    if not value:
        raise QWeatherConfigError("weather_api_host 未配置")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}:
        raise QWeatherConfigError("weather_api_host 必须是有效的 HTTPS API Host")
    return f"https://{parsed.netloc}"


def get_qw_lang(lang: str) -> str:
    if lang in {"zh-HK", "zh-TW"}:
        return "zh-hant"
    if lang.startswith("zh"):
        return "zh"
    if lang.startswith("en"):
        return "en"
    return lang


def get_local_data(ulang_code: str) -> dict[str, str]:
    ulang = Language(ulang_code)
    keys = (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "today",
        "tomorrow",
        "day",
        "night",
        "no_aqi",
        "now-windVelocity",
        "now-humidity",
        "now-feelsLike",
        "now-precip",
        "now-pressure",
        "now-vis",
        "now-cloud",
        "astronomy-sunrise",
        "astronomy-sunset",
    )
    return {key: ulang.get(f"weather.{key}") for key in keys}


def _coordinate(value: str, minimum: float, maximum: float, name: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError) as e:
        raise QWeatherDataError(f"城市返回了无效的{name}") from e
    if not minimum <= number <= maximum:
        raise QWeatherDataError(f"城市返回了超出范围的{name}")
    return f"{number:.6f}".rstrip("0").rstrip(".")


class QWeatherClient:
    def __init__(
        self,
        api_host: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_host = normalize_api_host(api_host)
        self.api_key = str(api_key or "").strip()
        if not self.api_key:
            raise QWeatherConfigError("weather_key 未配置")
        self._client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> "QWeatherClient":
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=HTTP_TIMEOUT,
                headers={"X-QW-Api-Key": self.api_key},
            )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("QWeatherClient must be used as an async context manager")
        try:
            response = await self._client.get(
                f"{self.api_host}{path}",
                params=params,
                headers={"X-QW-Api-Key": self.api_key},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as e:
            raise QWeatherError("请求和风天气超时，请稍后重试") from e
        except httpx.HTTPStatusError as e:
            raise QWeatherError(f"和风天气服务返回 HTTP {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise QWeatherError("无法连接和风天气服务，请稍后重试") from e
        except ValueError as e:
            raise QWeatherDataError("和风天气返回了无效 JSON") from e
        if not isinstance(payload, dict):
            raise QWeatherDataError("和风天气返回的数据格式无效")
        return payload

    async def city_lookup(
        self,
        location: str,
        adm: str = "",
        number: int = 10,
        lang: str = "zh",
    ) -> CityLookup:
        params: dict[str, Any] = {
            "location": location,
            "number": min(max(number, 1), 20),
            "lang": get_qw_lang(lang),
        }
        if adm:
            params["adm"] = adm
        payload = await self._get("/geo/v2/city/lookup", params)
        try:
            return CityLookup(**payload)
        except Exception as e:
            raise QWeatherDataError("城市搜索返回的数据格式无效") from e

    def _coordinates(self, location: Location) -> tuple[str, str]:
        return (
            _coordinate(location.lat, -90, 90, "纬度"),
            _coordinate(location.lon, -180, 180, "经度"),
        )

    async def weather_current(self, location: Location, lang: str = "zh") -> dict[str, Any]:
        lat, lon = self._coordinates(location)
        payload = await self._get(
            f"/weather/v1/current/{lat}/{lon}",
            {"lang": get_qw_lang(lang), "localTime": "true"},
        )
        if not isinstance(payload.get("condition"), dict):
            raise QWeatherDataError("实时天气数据缺少 condition")
        return payload

    async def weather_hourly(self, location: Location, lang: str = "zh") -> dict[str, Any]:
        lat, lon = self._coordinates(location)
        payload = await self._get(
            f"/weather/v1/hourly/{lat}/{lon}",
            {"lang": get_qw_lang(lang), "localTime": "true", "hours": 24},
        )
        if not isinstance(payload.get("hours"), list):
            raise QWeatherDataError("小时天气数据缺少 hours")
        return payload

    async def weather_daily(self, location: Location, lang: str = "zh") -> dict[str, Any]:
        lat, lon = self._coordinates(location)
        payload = await self._get(
            f"/weather/v1/daily/{lat}/{lon}",
            {"lang": get_qw_lang(lang), "localTime": "true", "days": 7},
        )
        if not isinstance(payload.get("days"), list):
            raise QWeatherDataError("每日天气数据缺少 days")
        return payload

    async def air_quality_current(
        self, location: Location, lang: str = "zh"
    ) -> dict[str, Any]:
        lat, lon = self._coordinates(location)
        payload = await self._get(
            f"/airquality/v1/current/{lat}/{lon}",
            {"lang": get_qw_lang(lang)},
        )
        if not isinstance(payload.get("indexes", []), list):
            raise QWeatherDataError("空气质量数据的 indexes 格式无效")
        return payload
