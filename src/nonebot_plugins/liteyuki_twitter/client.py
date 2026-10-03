"""Bounded HTTP access to configured Nitter instances and trusted media."""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urljoin, urlsplit

import aiohttp

from .config import TwitterConfig, normalize_account
from .models import SourceError
from .parser import parse_html, parse_rss

DOCUMENT_LIMIT = 3 * 1024 * 1024
IMAGE_LIMIT = 10 * 1024 * 1024


class NitterClient:
    def __init__(self, config: TwitterConfig):
        self.config = config
        self.session = None
        self.health: dict[str, dict] = {}
        self.blocked_until = 0

    async def start(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.config.twitter_timeout),
                                                  headers={"User-Agent": "LiteyukiBot-v6-LTS/Twitter"})

    async def close(self):
        if self.session is not None:
            await self.session.close()

    def allowed_url(self, url: str, *, media=False) -> bool:
        try:
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or parts.username or parts.password or not parts.hostname:
                return False
            origin = (parts.scheme, parts.hostname, parts.port)
            origins = {(p.scheme, p.hostname, p.port) for base in self.config.twitter_nitter_instances if (p := urlsplit(base))}
            if origin in origins:
                return True
            return media and parts.scheme == "https" and parts.port in {None, 443} and parts.hostname == "pbs.twimg.com"
        except ValueError:
            return False

    async def _request(self, url: str, *, media=False, max_bytes=DOCUMENT_LIMIT):
        await self.start()
        for _ in range(4):
            if not self.allowed_url(url, media=media):
                raise SourceError("来源或媒体重定向地址不在允许范围内")
            try:
                async with self.session.get(url, proxy=self.config.twitter_proxy or None, allow_redirects=False) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        url = urljoin(url, response.headers.get("Location", ""))
                        continue
                    if response.status != 200:
                        raise SourceError(f"Nitter 请求失败（HTTP {response.status}）", status=response.status,
                                          blocked=response.status in {401, 403, 429})
                    content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
                    if media and content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
                        raise SourceError("媒体格式不支持")
                    if response.content_length is not None and response.content_length > max_bytes:
                        raise SourceError("内容超过大小限制")
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        data.extend(chunk)
                        if len(data) > max_bytes:
                            raise SourceError("内容超过大小限制")
                    raw = bytes(data)
                    if not media:
                        lower = raw[:200000].lower()
                        challenge = any(marker in lower for marker in (b"cf-chl-", b"challenge-platform", b"anubis_challenge"))
                        wall = b"<rss" not in lower and b"tweet-content" not in lower and any(
                            marker in lower for marker in (b"captcha", b"sign in to x", b"log in to twitter"))
                        if challenge or wall:
                            raise SourceError("实例返回登录墙或验证页面", blocked=True)
                    return raw, content_type
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                raise SourceError("Nitter 网络连接失败或超时") from exc
        raise SourceError("重定向次数超过限制")

    def _failed(self, base: str, error: SourceError):
        previous = self.health.get(base, {})
        count = previous.get("failures", 0) + 1
        self.health[base] = {"failures": count, "until": time.monotonic() + min(3600, 60 * 2 ** min(count - 1, 6)),
                             "error": str(error)}

    async def _fetch(self, account: str, post_id: str | None = None):
        account = normalize_account(account)
        if post_id is not None and not post_id.isdigit():
            raise SourceError("推文 ID 无效")
        bases = self.config.twitter_nitter_instances
        if not bases:
            raise SourceError("尚未配置 Nitter 实例")
        if self.blocked_until > time.monotonic():
            raise SourceError("实例验证或限流退避中，请稍后再试", blocked=True)
        last = None
        for base in bases:
            if self.health.get(base, {}).get("until", 0) > time.monotonic():
                continue
            try:
                if post_id:
                    raw, _ = await self._request(f"{base}/{account}/status/{post_id}")
                    posts = parse_html(raw.decode("utf-8", errors="replace"), base, account, status_id=post_id)
                else:
                    try:
                        raw, _ = await self._request(f"{base}/{account}/rss")
                        posts = parse_rss(raw, base, account)
                    except SourceError as error:
                        if error.status not in {404, 405, 410, 501}:
                            raise
                        raw, _ = await self._request(f"{base}/{account}")
                        posts = parse_html(raw.decode("utf-8", errors="replace"), base, account)
                self.health[base] = {"failures": 0, "until": 0, "error": ""}
                return posts
            except SourceError as error:
                last = error
                self._failed(base, error)
                if error.blocked:
                    # Do not cycle through mirrors to evade login/captcha/rate limits.
                    self.blocked_until = self.health[base]["until"]
                    raise
        raise last or SourceError("所有 Nitter 实例均在退避等待中")

    async def get_timeline(self, account: str):
        return await self._fetch(account)

    async def get_status(self, account: str, post_id: str):
        return (await self._fetch(account, post_id))[0]

    async def download_image(self, url: str, max_bytes: int = IMAGE_LIMIT):
        raw, content_type = await self._request(url, media=True, max_bytes=min(max_bytes, IMAGE_LIMIT))
        return raw, content_type
