from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import aiohttp
from nonebot import logger

from .models import ProviderError


class HttpClient:
    """One small HTTP boundary shared by all providers and image downloads."""

    def __init__(self, timeout: float, retries: int = 2, session: aiohttp.ClientSession | None = None):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.retries = retries
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> "HttpClient":
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"User-Agent": "LiteyukiBot-v6-LTS/setu-safe"},
            )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()

    async def request_json(self, method: str, url: str, *, params: Mapping[str, Any] | None = None,
                           json: Mapping[str, Any] | None = None, proxy: str | None = None) -> Any:
        session = self._session
        if session is None:
            async with self as client:
                return await client.request_json(method, url, params=params, json=json, proxy=proxy)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with session.request(method, url, params=params, json=json, proxy=proxy,
                                           allow_redirects=True) as response:
                    if 400 <= response.status < 500:
                        raise ProviderError(f"HTTP {response.status}")
                    if not 200 <= response.status < 300:
                        raise _RetryableError(f"HTTP {response.status}")
                    try:
                        return await response.json(content_type=None)
                    except (aiohttp.ContentTypeError, ValueError) as exc:
                        raise ProviderError("图片源返回了无效 JSON") from exc
            except _RetryableError as exc:
                last_error = exc
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
            if attempt < self.retries:
                await asyncio.sleep(0.2 * (attempt + 1))
        reason = _error_reason(last_error)
        logger.warning(f"HTTP JSON 请求失败: host={_host(url)}, reason={reason}")
        raise ProviderError(f"图片源请求失败: {reason}") from last_error

    async def download_image(self, url: str, *, max_bytes: int,
                             headers: Mapping[str, str] | None = None,
                             proxy: str | None = None) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ProviderError("图片地址无效")
        session = self._session
        if session is None:
            async with self as client:
                return await client.download_image(url, max_bytes=max_bytes, headers=headers, proxy=proxy)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with session.get(url, headers=headers, proxy=proxy, allow_redirects=True) as response:
                    if 400 <= response.status < 500:
                        raise ProviderError(f"图片 HTTP {response.status}")
                    if not 200 <= response.status < 300:
                        raise _RetryableError(f"图片 HTTP {response.status}")
                    content_type = response.headers.get("Content-Type", "").lower()
                    if not content_type.startswith("image/"):
                        raise ProviderError("图片响应不是图片")
                    body = await response.read()
                    if not body or len(body) > max_bytes:
                        raise ProviderError("图片为空或超过大小限制")
                    self._verify_image(body)
                    return body
            except _RetryableError as exc:
                last_error = exc
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
            if attempt < self.retries:
                await asyncio.sleep(0.2 * (attempt + 1))
        reason = _error_reason(last_error)
        logger.warning(f"图片下载失败: host={parsed.hostname or ''}, reason={reason}")
        raise ProviderError(f"图片下载失败: {reason}") from last_error

    @staticmethod
    def _verify_image(body: bytes) -> None:
        try:
            from PIL import Image
            from io import BytesIO
            with Image.open(BytesIO(body)) as image:
                image.verify()
        except ImportError:
            return
        except Exception as exc:
            raise ProviderError("图片数据损坏") from exc


def _host(url: str) -> str:
    return urlparse(url).hostname or ""


def _error_reason(error: Exception | None) -> str:
    if error is None:
        return "unknown"
    detail = str(error).strip()
    detail = re.sub(r"(https?://)[^/@\s]+@", r"\1***@", detail)
    return f"{type(error).__name__}: {detail}" if detail else type(error).__name__


class _RetryableError(RuntimeError):
    pass
