from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, replace
from typing import Any, Literal
from urllib.parse import urlparse

from nonebot import logger

from .config import SetuConfig
from .models import (ImageQuery, ImageResult, NetworkError, NoResultError, ProviderError,
                     ProviderUnavailableError, UnsupportedQueryError, is_result_allowed)
from .network import HttpClient
from .providers.registry import PROVIDER_REGISTRY, get_provider_spec
from .recent import DedupLease, RecentDeduplicator

_PIXIV_HEADERS = {"Referer": "https://www.pixiv.net/", "User-Agent": "Mozilla/5.0"}


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

    def reserve(
        self, key: str, seconds: int, bypass: bool = False,
    ) -> Literal["ok", "pending", "cooldown"]:
        now = time.monotonic()
        if key in self._pending:
            return "pending"
        if not bypass and now - self._success.get(key, float("-inf")) < seconds:
            return "cooldown"
        self._pending.add(key)
        return "ok"

    def finish(self, key: str, sent: bool) -> None:
        self._pending.discard(key)
        if sent:
            self._success[key] = time.monotonic()


health = ProviderHealth()
cooldown = Cooldown()
recent_dedup = RecentDeduplicator()
_dedup_leases: dict[int, tuple[ImageResult, DedupLease]] = {}


def _api_timeout(config: SetuConfig) -> float:
    return config.setu_api_timeout or config.setu_request_timeout


def _image_timeout(config: SetuConfig) -> float:
    return config.setu_image_timeout or config.setu_request_timeout


def _provider_name(provider: Any) -> str:
    name = getattr(provider, "name", getattr(provider, "provider", ""))
    spec = get_provider_spec(str(name))
    return spec.display_name if spec else str(name)


def _image_options(result: ImageResult, url: str,
                   config: SetuConfig) -> tuple[dict[str, str] | None, str | None]:
    host = urlparse(url).hostname
    headers = _PIXIV_HEADERS if host == "i.pximg.net" else None
    proxy = config.setu_image_http_proxy or None
    if result.provider == "lolicon" and config.setu_lolicon_image_http_proxy:
        proxy = config.setu_lolicon_image_http_proxy
    return headers, proxy


def build_providers(config: SetuConfig, client: HttpClient) -> dict[str, Any]:
    return {name: spec.factory(client, config) for name, spec in PROVIDER_REGISTRY.items()}


def _enabled(name: str, config: SetuConfig) -> bool:
    return bool(getattr(config, f"setu_{name}_enabled", False))


def _rating_allowed(name: str, query: ImageQuery, config: SetuConfig, *, explicit: bool) -> bool:
    spec = get_provider_spec(name)
    rating_mode = spec.rating_mode if spec else "unclassified"
    if query.r18:
        return rating_mode in {"filterable", "bucketed"}
    if rating_mode == "unclassified" and not explicit:
        return bool(getattr(config, f"setu_{name}_random_pool_enabled", False))
    return True


def _weighted_order(providers: list[Any], config: SetuConfig) -> list[Any]:
    remaining = [provider for provider in providers
                 if config.setu_provider_weights.get(provider.name, 0) > 0]
    ordered: list[Any] = []
    while remaining:
        weights = [config.setu_provider_weights.get(provider.name, 0) for provider in remaining]
        selected = random.choices(remaining, weights=weights, k=1)[0]
        ordered.append(selected)
        remaining.remove(selected)
    return ordered


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
        if not _rating_allowed(name, query, config, explicit=explicit):
            if explicit:
                raise UnsupportedQueryError("该图片源不支持请求的内容分级。")
            continue
        if not provider.supports(query):
            if explicit:
                raise UnsupportedQueryError("该图片源不支持此筛选条件。")
            continue
        if not health.available(name):
            if explicit:
                raise ProviderUnavailableError(f"{name} 因连续失败已暂时熔断，请稍后重试。")
            continue
        selected.append(provider)
    if not explicit:
        selected = _weighted_order(selected, config)
    if not selected:
        if explicit:
            raise ProviderUnavailableError(f"{query.provider} 当前不可用，请稍后重试或使用 --source auto。")
        raise UnsupportedQueryError("没有可用图片源支持当前筛选条件。")
    return selected


async def fetch_images(query: ImageQuery, config: SetuConfig, *, client: HttpClient | None = None) -> list[ImageResult]:
    if client is None:
        async with HttpClient(
            _api_timeout(config), config.setu_request_retries,
            default_proxy=config.setu_api_http_proxy or None,
        ) as owned:
            return await fetch_images(query, config, client=owned)
    providers = build_providers(config, client)
    last_error: Exception | None = None
    saw_no_result = False
    for provider in choose_providers(query, config, providers):
        try:
            results = [result for result in await provider.fetch(query) if is_result_allowed(result, r18=query.r18)]
            if not results:
                raise NoResultError("没有找到符合条件的图片。")
            health.success(provider.name)
            return results[:query.count]
        except NoResultError:
            # An empty search is a valid answer and must not be treated as an outage.
            if query.provider != "auto":
                raise
            saw_no_result = True
            continue
        except ProviderError as exc:
            logger.warning(f"{_provider_name(provider)} API 请求失败: {exc}")
            health.failure(provider.name, config, exc)
            last_error = exc
            if query.provider != "auto":
                raise ProviderUnavailableError(f"{provider.name} 本次请求失败，请稍后重试。") from exc
    if saw_no_result:
        raise NoResultError("没有找到符合条件的图片。")
    if last_error:
        raise ProviderUnavailableError("图片源暂时不可用，请稍后再试。") from last_error
    raise UnsupportedQueryError("没有可用图片源支持当前筛选条件。")


class DownloadedResults(list[tuple[ImageResult, bytes]]):
    def __init__(self, values: list[tuple[ImageResult, bytes]], failed_network_hosts: list[str]):
        super().__init__(values)
        self.failed_network_hosts = failed_network_hosts


def _is_network_failure(error: ProviderError) -> bool:
    if isinstance(error, NetworkError):
        return True
    detail = str(error).lower()
    return any(token in detail for token in (
        "timeout", "dns", "connection", "connector", "reset", "refused", "network",
        "retryableerror",
    ))


async def download_results(results: list[ImageResult], config: SetuConfig, *, client: HttpClient | None = None) -> list[tuple[ImageResult, bytes]]:
    if client is None:
        async with HttpClient(
            _image_timeout(config), config.setu_request_retries,
            default_proxy=config.setu_image_http_proxy or None,
        ) as owned:
            return await download_results(results, config, client=owned)
    semaphore = asyncio.Semaphore(config.setu_download_concurrency)

    async def download(result: ImageResult) -> tuple[tuple[ImageResult, bytes] | None, str | None]:
        candidates = list(dict.fromkeys([result.image_url, *result.fallback_image_urls]))
        primary_error: ProviderError | None = None
        for position, url in enumerate(candidates):
            headers, proxy = _image_options(result, url, config)
            try:
                async with semaphore:
                    options: dict[str, Any] = {}
                    if result.fallback_image_urls:
                        options = {
                            "timeout": config.setu_image_candidate_timeout,
                            "retries": config.setu_image_candidate_retries,
                        }
                    raw = await client.download_image(
                        url, max_bytes=config.setu_image_max_bytes, headers=headers,
                        proxy=proxy, **options,
                    )
                if position:
                    logger.info(f"{_provider_name(result)} 图片备用地址下载成功: host={urlparse(url).hostname or ''}")
                return (result, raw), None
            except ProviderError as exc:
                if position == 0:
                    primary_error = exc
                host = urlparse(url).hostname or ""
                logger.warning(f"{_provider_name(result)} 图片下载失败: host={host}, reason={exc}")
        failed_host = urlparse(result.image_url).hostname or ""
        if primary_error is None or not _is_network_failure(primary_error):
            failed_host = ""
        return None, failed_host or None

    downloaded = await asyncio.gather(*(download(result) for result in results))
    values = [item for item, _host in downloaded if item is not None]
    failed_hosts = [host for _item, host in downloaded if host is not None]
    return DownloadedResults(values, failed_hosts)


def _result_key(result: ImageResult) -> tuple[str, str]:
    if result.pid is not None:
        return "pid", str(result.pid)
    return "url", result.image_url


def _dedup_ttl(config: SetuConfig) -> float:
    return config.setu_recent_dedup_hours * 3600.0


def commit_result(result: ImageResult, config: SetuConfig) -> None:
    reserved = _dedup_leases.pop(id(result), None)
    if reserved is None or reserved[0] is not result:
        return
    recent_dedup.commit(
        reserved[1], ttl_seconds=_dedup_ttl(config),
        max_entries=config.setu_recent_dedup_max_entries,
    )


def release_result(result: ImageResult) -> None:
    reserved = _dedup_leases.pop(id(result), None)
    if reserved is not None and reserved[0] is result:
        recent_dedup.release(reserved[1])


def release_results(results: list[tuple[ImageResult, bytes]]) -> None:
    for result, _raw in results:
        release_result(result)


async def _fetch_with_refills(provider: Any, query: ImageQuery, config: SetuConfig,
                              image_client: HttpClient) -> list[tuple[ImageResult, bytes]]:
    successful: list[tuple[ImageResult, bytes]] = []
    seen: set[tuple[str, str]] = set()
    saw_recent_duplicate = False
    saw_download_failure = False
    last_failed_host = ""
    failed_host_streak = 0
    max_attempts = 1 + config.setu_recent_dedup_refill_attempts
    for attempt in range(max_attempts):
        missing = query.count - len(successful)
        if missing <= 0:
            break
        if attempt:
            logger.info(
                f"{_provider_name(provider)} 补图: missing={missing} "
                f"attempt={attempt}/{max_attempts - 1}"
            )
        refill_query = query if attempt == 0 else replace(query, count=missing)
        try:
            returned = await provider.fetch(refill_query)
        except NoResultError:
            if successful:
                logger.info(f"{_provider_name(provider)} 补图无结果，保留已下载图片。")
                break
            raise
        except ProviderError as exc:
            if successful:
                logger.warning(f"{_provider_name(provider)} 补图请求失败，保留已下载图片: {exc}")
                break
            raise
        accepted: list[ImageResult] = []
        leases: dict[int, DedupLease] = {}
        for result in returned:
            result_key = _result_key(result)
            if not is_result_allowed(result, r18=query.r18) or result_key in seen:
                continue
            seen.add(result_key)
            if config.setu_recent_dedup_enabled and not query.pid:
                lease = recent_dedup.reserve(
                    result, ttl_seconds=_dedup_ttl(config),
                    max_entries=config.setu_recent_dedup_max_entries,
                )
                if lease is None:
                    saw_recent_duplicate = True
                    continue
                leases[id(result)] = lease
            accepted.append(result)
        logger.info(f"{_provider_name(provider)} 图片结果: requested={missing} returned={len(returned)} accepted={len(accepted)}")
        try:
            downloaded = await download_results(accepted, config, client=image_client)
        except BaseException:
            for lease in leases.values():
                recent_dedup.release(lease)
            raise
        downloaded_ids = {id(result) for result, _raw in downloaded}
        for result in accepted:
            if id(result) not in downloaded_ids and id(result) in leases:
                recent_dedup.release(leases[id(result)])
        usable: list[tuple[ImageResult, bytes]] = []
        for result, raw in downloaded:
            lease = leases.get(id(result))
            if lease is not None:
                if not recent_dedup.reserve_hash(lease, raw):
                    recent_dedup.release(lease)
                    saw_recent_duplicate = True
                    continue
                _dedup_leases[id(result)] = (result, lease)
            usable.append((result, raw))
        saw_download_failure = saw_download_failure or len(downloaded) < len(accepted)
        successful.extend(usable[:missing])
        for extra_result, _raw in usable[missing:]:
            release_result(extra_result)
        logger.info(
            f"{_provider_name(provider)} 图片下载: success={len(usable)} "
            f"failed={len(accepted) - len(downloaded)} duplicate={len(downloaded) - len(usable)}"
        )
        failed_host = ""
        for host in getattr(downloaded, "failed_network_hosts", []):
            if host == last_failed_host:
                failed_host_streak += 1
            else:
                last_failed_host = host
                failed_host_streak = 1
            if failed_host_streak >= 2:
                failed_host = host
                break
        if failed_host:
            logger.warning(f"{_provider_name(provider)} 同一图片主机连续失败，停止补图: host={failed_host}")
            if not successful:
                raise ProviderError(f"图片主机连续不可用: {failed_host}")
            break
    logger.info(f"{_provider_name(provider)} 图片获取完成: requested={query.count} downloaded={len(successful)}")
    if not successful and saw_recent_duplicate and not saw_download_failure:
        raise NoResultError("没有找到近期未发送过的图片。")
    return successful[:query.count]


async def fetch_and_download(query: ImageQuery, config: SetuConfig) -> list[tuple[ImageResult, bytes]]:
    """Fallback only to providers that can express exactly the current query."""
    async with HttpClient(
        _api_timeout(config), config.setu_request_retries,
        default_proxy=config.setu_api_http_proxy or None,
    ) as api_client:
        providers = build_providers(config, api_client)
        last_error: Exception | None = None
        saw_no_result = False
        for provider in choose_providers(query, config, providers):
            try:
                async with HttpClient(
                    _image_timeout(config), config.setu_request_retries,
                    default_proxy=config.setu_image_http_proxy or None,
                ) as image_client:
                    downloaded = await _fetch_with_refills(provider, query, config, image_client)
                if not downloaded:
                    raise ProviderError("没有图片下载成功")
                health.success(provider.name)
                return downloaded
            except NoResultError:
                if query.provider != "auto":
                    raise
                saw_no_result = True
                continue
            except ProviderError as exc:
                logger.warning(f"{_provider_name(provider)} 图片获取失败: {exc}")
                health.failure(provider.name, config, exc)
                last_error = exc
                if query.provider != "auto":
                    raise ProviderUnavailableError(f"{provider.name} 本次请求失败，请稍后重试。") from exc
        if saw_no_result:
            raise NoResultError("没有找到符合条件的图片。")
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
    lines.append(f"来源：{_provider_name(result)}")
    return "\n".join(lines)
