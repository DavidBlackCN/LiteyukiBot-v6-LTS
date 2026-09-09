from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp


class SixtyApiError(RuntimeError):
    """A controlled failure returned by a 60s API instance."""


class SixtyApiClient:
    def __init__(self, base_url: str, timeout: float = 10, session: aiohttp.ClientSession | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session = session
        self._owns_session = session is None

    def endpoint(self, path: str) -> str:
        """Append instead of urljoin so a configured path prefix is retained."""
        return f"{self.base_url}/{path.lstrip('/')}"

    async def __aenter__(self) -> "SixtyApiClient":
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"User-Agent": "LiteyukiBot-v6-LTS/60s-plugin"},
            )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()

    async def get_data(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        session = self._session
        if session is None:
            async with self as client:
                return await client.get_data(path, params=params)
        try:
            async with session.get(self.endpoint(path), params=params, allow_redirects=True) as response:
                if not 200 <= response.status < 300:
                    raise SixtyApiError(f"HTTP {response.status}")
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as exc:
                    raise SixtyApiError("响应不是有效 JSON") from exc
        except asyncio.TimeoutError as exc:
            raise SixtyApiError("请求超时") from exc
        except aiohttp.ClientError as exc:
            raise SixtyApiError("网络请求失败") from exc
        if not isinstance(payload, dict) or payload.get("code") != 200:
            message = payload.get("message") if isinstance(payload, dict) else "无效响应"
            raise SixtyApiError(f"API 返回失败：{message}")
        if payload.get("data") is None:
            raise SixtyApiError("API 未返回数据")
        return payload["data"]

    async def download_image(self, url: str) -> bytes:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SixtyApiError("图片地址无效")
        session = self._session
        if session is None:
            async with self as client:
                return await client.download_image(url)
        try:
            async with session.get(urlunsplit(parsed), allow_redirects=True) as response:
                if not 200 <= response.status < 300:
                    raise SixtyApiError(f"图片 HTTP {response.status}")
                image = await response.read()
        except asyncio.TimeoutError as exc:
            raise SixtyApiError("图片下载超时") from exc
        except aiohttp.ClientError as exc:
            raise SixtyApiError("图片下载失败") from exc
        if not image:
            raise SixtyApiError("图片为空")
        return image


import asyncio
