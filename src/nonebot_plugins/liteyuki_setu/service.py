from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from .config import SetuConfig
from .models import (ImageQuery, ImageResult, NoResultError, ProviderError,
                     ProviderUnavailableError, UnsupportedQueryError, is_result_allowed)
from .network import HttpClient
from .providers import LoliconProvider, MirlKoiProvider


@dataclass
class _Health:
    failures: int = 0
    unhealthy_until: float = 0
    last_error: str = ""


class ProviderHealth:
    def __init__(self) -> None:
        self._items: dict[str, _Health] = {}

    def available(self, name: str) -> bool:
        return self._items.get(name, _Health()).unhealthy_until <= time.monotonic()

    def success(self, name: str) -> None:
        self._items[name] = _Health()

    def failure(self, name: str, config: SetuConfig, error: Exception) -> None:
        state = self._items.setdefault(name, _Health())
        state.failures += 1
        state.last_error = str(error)
        if state.failures >= config.setu_provider_failure_threshold:
            state.unhealthy_until = time.monotonic() + config.setu_provider_cooldown_seconds


class Cooldown:
    def __init__(self) -> None:
        self._success: dict[str, float] = {}
        self._pending: set[str] = set()

    def reserve(self, key: str, seconds: int, bypass: bool = False) -> bool:
        now = time.monotonic()
        if key in self._pending:
            return False
        if not bypass and now - self._success.get(key, float("-inf")) < seconds:
            return False
        self._pending.add(key)
        return True

    def finish(self, key: str, sent: bool) -> None:
        self._pending.discard(key)
        if sent:
            self._success[key] = time.monotonic()


health = ProviderHealth()
cooldown = Cooldown()


def build_providers(config: SetuConfig, client: HttpClient) -> dict[str, Any]:
    return {
        "lolicon": LoliconProvider(client, config.setu_lolicon_api_url, config.setu_pixiv_proxy),
        "mirlkoi": MirlKoiProvider(client, config.setu_mirlkoi_base_url, config.setu_mirlkoi_endpoint),
    }


def _enabled(name: str, config: SetuConfig) -> bool:
    return bool(getattr(config, f"setu_{name}_enabled", False))


def choose_providers(query: ImageQuery, config: SetuConfig, providers: dict[str, Any]) -> list[Any]:
    names = [query.provider] if query.provider != "auto" else config.setu_provider_order
    selected: list[Any] = []
    explicit = query.provider != "auto"
    for name in names:
        provider = providers.get(name)
        if provider is None or not _enabled(name, config):
            continue
        if not provider.safe_available:
            continue
        if not provider.supports(query):
            if explicit:
                raise UnsupportedQueryError("该图片源不支持此筛选条件。")
            continue
        if not health.available(name):
            continue
        selected.append(provider)
    if not selected:
        if explicit:
            raise ProviderUnavailableError(f"{query.provider} 当前不可用，请稍后重试或使用 --source auto。")
        raise UnsupportedQueryError("没有可用图片源支持当前筛选条件。")
    return selected


async def fetch_images(query: ImageQuery, config: SetuConfig, *, client: HttpClient | None = None) -> list[ImageResult]:
    if client is None:
        async with HttpClient(config.setu_request_timeout, config.setu_request_retries) as owned:
            return await fetch_images(query, config, client=owned)
    providers = build_providers(config, client)
    last_error: Exception | None = None
    for provider in choose_providers(query, config, providers):
        try:
            results = [result for result in await provider.fetch(query) if is_result_allowed(result, r18=query.r18)]
            if not results:
                raise NoResultError("没有找到符合条件的图片。")
            health.success(provider.name)
            return results[:query.count]
        except NoResultError:
            # An empty search is a valid answer and must not be treated as an outage.
            raise
        except ProviderError as exc:
            health.failure(provider.name, config, exc)
            last_error = exc
            if query.provider != "auto":
                raise ProviderUnavailableError(f"{provider.name} 当前不可用，请稍后重试或使用 --source auto。") from exc
    if last_error:
        raise ProviderUnavailableError("图片源暂时不可用，请稍后再试。") from last_error
    raise UnsupportedQueryError("没有可用图片源支持当前筛选条件。")


async def download_results(results: list[ImageResult], config: SetuConfig, *, client: HttpClient | None = None) -> list[tuple[ImageResult, bytes]]:
    if client is None:
        async with HttpClient(config.setu_request_timeout, config.setu_request_retries) as owned:
            return await download_results(results, config, client=owned)
    semaphore = asyncio.Semaphore(config.setu_download_concurrency)

    async def download(result: ImageResult) -> tuple[ImageResult, bytes] | None:
        try:
            async with semaphore:
                return result, await client.download_image(result.image_url, max_bytes=config.setu_image_max_bytes)
        except ProviderError:
            return None

    downloaded = await asyncio.gather(*(download(result) for result in results))
    return [item for item in downloaded if item is not None]

async def fetch_and_download(query: ImageQuery, config: SetuConfig) -> list[tuple[ImageResult, bytes]]:
    """Fallback only to providers that can express exactly the current query."""
    async with HttpClient(config.setu_request_timeout, config.setu_request_retries) as client:
        providers = build_providers(config, client)
        last_error: Exception | None = None
        for provider in choose_providers(query, config, providers):
            try:
                results = [result for result in await provider.fetch(query) if is_result_allowed(result, r18=query.r18)]
                if not results:
                    raise NoResultError("没有找到符合条件的图片。")
                downloaded = await download_results(results[:query.count], config, client=client)
                if not downloaded:
                    raise ProviderError("图片下载失败")
                health.success(provider.name)
                return downloaded
            except NoResultError:
                raise
            except ProviderError as exc:
                health.failure(provider.name, config, exc)
                last_error = exc
                if query.provider != "auto":
                    raise ProviderUnavailableError(f"{provider.name} 当前不可用，请稍后重试或使用 --source auto。") from exc
        if last_error:
            raise ProviderUnavailableError("图片源暂时不可用，请稍后再试。") from last_error
        raise UnsupportedQueryError("没有可用图片源支持当前筛选条件。")

def metadata_text(result: ImageResult) -> str:
    lines: list[str] = []
    if result.title:
        lines.append(f"标题：{result.title}")
    if result.author:
        lines.append(f"画师：{result.author}")
    if result.pid is not None:
        lines.append(f"PID：{result.pid}")
    lines.append(f"来源：{result.provider.title()}")
    return "\n".join(lines)
