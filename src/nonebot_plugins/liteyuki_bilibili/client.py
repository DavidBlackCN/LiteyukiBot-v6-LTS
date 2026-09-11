"""Shared, bounded HTTP client for Bilibili read APIs and QR login."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from .config import BilibiliConfig
from .credential import CredentialManager, parse_cookie, serialize_cookie
from .errors import (
    BilibiliAPIError,
    BilibiliCredentialError,
    BilibiliNetworkError,
    BilibiliRateLimitError,
)
from .models import (
    BilibiliEvent,
    BilibiliLiveStatus,
    BilibiliNav,
    BilibiliQRCode,
    BilibiliQRLoginResult,
    BilibiliUser,
    BilibiliVideo,
)


API_BASE = "https://api.bilibili.com"
LIVE_API_BASE = "https://api.live.bilibili.com"
_SHORT_LINK_HOSTS = {"b23.tv", "www.b23.tv"}
_ALLOWED_HOSTS = _SHORT_LINK_HOSTS | {
    "bilibili.com",
    "www.bilibili.com",
    "m.bilibili.com",
    "live.bilibili.com",
    "t.bilibili.com",
    "space.bilibili.com",
}
_IMAGE_HOSTS = {"i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com"}
_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@dataclass(frozen=True)
class DownloadedImage:
    data: bytes
    content_type: str


class BilibiliClient:
    """Long-lived client. Construct once in the future service lifecycle."""

    def __init__(
        self,
        config: BilibiliConfig,
        credentials: CredentialManager,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.credentials = credentials
        self._client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> "BilibiliClient":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._client is not None:
            return
        options: dict[str, Any] = {
            "timeout": httpx.Timeout(self.config.bilibili_api_timeout),
            "follow_redirects": False,
        }
        if self.config.bilibili_proxy.strip():
            options["proxy"] = self.config.bilibili_proxy.strip()
        self._client = httpx.AsyncClient(**options)

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
        self._client = None

    async def get_nav(self) -> BilibiliNav:
        data = await self._api_get(f"{API_BASE}/x/web-interface/nav")
        return BilibiliNav(
            is_login=bool(data.get("isLogin", False)),
            mid=str(data.get("mid") or ""),
            username=str(data.get("uname") or ""),
        )

    async def get_user_info(self, uid: str) -> BilibiliUser:
        data = await self._api_get(
            f"{API_BASE}/x/space/wbi/acc/info", {"mid": str(uid)}
        )
        return BilibiliUser(
            uid=str(data.get("mid") or uid),
            name=str(data.get("name") or ""),
            avatar_url=str(data.get("face") or ""),
        )

    async def get_latest_videos(self, uid: str) -> list[BilibiliVideo]:
        data = await self._api_get(
            f"{API_BASE}/x/space/wbi/arc/search",
            {"mid": str(uid), "pn": 1, "ps": 3, "order": "pubdate"},
        )
        listing = data.get("list") if isinstance(data.get("list"), dict) else {}
        videos = listing.get("vlist") if isinstance(listing.get("vlist"), list) else []
        return [self._video_from_api(video) for video in videos if isinstance(video, dict)]

    async def get_latest_dynamics(self, uid: str) -> list[BilibiliEvent]:
        data = await self._api_get(
            f"{API_BASE}/x/polymer/web-dynamic/v1/feed/space",
            {"host_mid": str(uid)},
        )
        items = data.get("items") if isinstance(data.get("items"), list) else []
        return [
            self._dynamic_from_api(item, fallback_uid=str(uid))
            for item in items
            if isinstance(item, dict)
        ]

    async def get_live_status(self, uid: str) -> BilibiliLiveStatus:
        data = await self._api_get(
            f"{LIVE_API_BASE}/room/v1/Room/getRoomInfoOld", {"mid": str(uid)}
        )
        room_id = str(data.get("room_id") or "")
        return BilibiliLiveStatus(
            uid=str(uid),
            room_id=room_id,
            live=bool(data.get("live_status")),
            title=str(data.get("title") or ""),
            area_name=str(data.get("area_name") or ""),
            cover_url=str(data.get("user_cover") or data.get("cover") or ""),
            url=f"https://live.bilibili.com/{room_id}" if room_id else "",
        )

    async def get_video_info(self, *, bvid: str = "", aid: str = "") -> BilibiliVideo:
        if not bvid and not aid:
            raise ValueError("bvid or aid is required")
        params = {"bvid": bvid} if bvid else {"aid": aid}
        return self._video_from_api(
            await self._api_get(f"{API_BASE}/x/web-interface/view", params)
        )

    async def get_dynamic_detail(self, dynamic_id: str) -> BilibiliEvent:
        data = await self._api_get(
            f"{API_BASE}/x/polymer/web-dynamic/v1/detail", {"id": str(dynamic_id)}
        )
        item = data.get("item")
        if not isinstance(item, dict):
            raise BilibiliAPIError("Bilibili dynamic detail was incomplete")
        return self._dynamic_from_api(item)

    async def create_qr_login(self) -> BilibiliQRCode:
        data = await self._api_get(f"{API_BASE}/x/passport-login/web/qrcode/generate")
        url = str(data.get("url") or "")
        key = str(data.get("qrcode_key") or "")
        if not url or not key:
            raise BilibiliAPIError("QR login response was incomplete")
        return BilibiliQRCode(url=url, key=key)

    async def poll_qr_login(self, key: str) -> BilibiliQRLoginResult:
        response = await self._request(
            "GET",
            f"{API_BASE}/x/passport-login/web/qrcode/poll",
            {"qrcode_key": key},
        )
        payload = self._json(response)
        code = payload.get("code")
        if code == 86101:
            return BilibiliQRLoginResult(status="waiting")
        if code == 86090:
            return BilibiliQRLoginResult(status="scanned")
        if code == 86038:
            return BilibiliQRLoginResult(status="expired")
        if code != 0:
            self._raise_api_code(code)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BilibiliAPIError("QR login response data was invalid")
        cookies: dict[str, str] = {}
        for header in response.headers.get_list("set-cookie"):
            cookies.update(parse_cookie(header.split(";", 1)[0]))
        return BilibiliQRLoginResult(
            status="confirmed",
            cookie=serialize_cookie(cookies),
            refresh_token=str(data.get("refresh_token") or ""),
        )

    async def resolve_short_url(self, url: str, max_redirects: int = 3) -> str:
        current = self._validate_short_url(url, require_short_host=True)
        for _ in range(max_redirects):
            response = await self._request("GET", current)
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise BilibiliAPIError("Bilibili short link did not provide a location")
                current = self._validate_short_url(urljoin(current, location))
                continue
            if response.is_success:
                return current
            raise BilibiliNetworkError(f"Short link returned HTTP {response.status_code}")
        raise BilibiliAPIError("Bilibili short link exceeded redirect limit")

    async def download_image(self, url: str, max_bytes: int = 4 * 1024 * 1024) -> DownloadedImage:
        """Download only trusted Bilibili CDN images for local card embedding."""
        parsed = urlsplit(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in _IMAGE_HOSTS:
            raise BilibiliAPIError("Bilibili image host was not allowed")
        if self._client is None:
            raise RuntimeError("BilibiliClient must be started before use")
        try:
            async with self._client.stream(
                "GET",
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 LiteyukiBot-v6-LTS Bilibili Service",
                    "Referer": "https://www.bilibili.com/",
                },
            ) as response:
                if response.is_error:
                    raise BilibiliNetworkError(f"Bilibili image returned HTTP {response.status_code}")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type not in _IMAGE_CONTENT_TYPES:
                    raise BilibiliAPIError("Bilibili image returned an unsupported content type")
                declared_size = response.headers.get("content-length")
                if declared_size and int(declared_size) > max_bytes:
                    raise BilibiliAPIError("Bilibili image exceeded size limit")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > max_bytes:
                        raise BilibiliAPIError("Bilibili image exceeded size limit")
        except ValueError as exc:
            raise BilibiliAPIError("Bilibili image returned an invalid content length") from exc
        except httpx.HTTPError as exc:
            raise BilibiliNetworkError("Bilibili image request failed") from exc
        return DownloadedImage(bytes(chunks), content_type)

    async def _api_get(
        self, url: str, params: Mapping[str, str | int] | None = None
    ) -> dict[str, Any]:
        response = await self._request("GET", url, params)
        payload = self._json(response)
        self._raise_api_code(payload.get("code"))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BilibiliAPIError("Bilibili API returned invalid data")
        return data

    async def _request(
        self,
        method: str,
        url: str,
        params: Mapping[str, str | int] | None = None,
    ) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("BilibiliClient must be started before use")
        headers = {
            "User-Agent": "Mozilla/5.0 LiteyukiBot-v6-LTS Bilibili Service",
            "Referer": "https://www.bilibili.com/",
            "Accept": "application/json, text/plain, */*",
        }
        cookie = self.credentials.get().cookie_header
        if cookie:
            headers["Cookie"] = cookie
        try:
            response = await self._client.request(method, url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise BilibiliNetworkError("Bilibili request timed out") from exc
        except httpx.HTTPError as exc:
            raise BilibiliNetworkError("Bilibili request failed") from exc
        if response.status_code == 412:
            raise BilibiliRateLimitError("Bilibili anti-crawling response")
        if response.status_code in {401, 403}:
            raise BilibiliCredentialError(f"Bilibili returned HTTP {response.status_code}")
        if response.is_error:
            raise BilibiliNetworkError(f"Bilibili returned HTTP {response.status_code}")
        return response

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BilibiliAPIError("Bilibili returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise BilibiliAPIError("Bilibili returned a non-object JSON payload")
        return payload

    @staticmethod
    def _raise_api_code(code: object) -> None:
        if code == 0:
            return
        if code == -101:
            raise BilibiliCredentialError("Bilibili credential is invalid")
        if code == -412:
            raise BilibiliRateLimitError("Bilibili API anti-crawling response")
        raise BilibiliAPIError(f"Bilibili API returned code {code!r}")

    @staticmethod
    def _validate_short_url(url: str, require_short_host: bool = False) -> str:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            raise BilibiliAPIError("Bilibili short link URL was invalid")
        if require_short_host and host not in _SHORT_LINK_HOSTS:
            raise BilibiliAPIError("URL is not a Bilibili short link")
        if host not in _ALLOWED_HOSTS:
            raise BilibiliAPIError("Bilibili short link redirected to an untrusted host")
        return url

    @staticmethod
    def _video_from_api(data: Mapping[str, Any]) -> BilibiliVideo:
        owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
        stat = data.get("stat") if isinstance(data.get("stat"), dict) else {}
        bvid = str(data.get("bvid") or "")
        aid = str(data.get("aid") or data.get("id") or "")
        timestamp = _timestamp(data.get("pubdate") or data.get("created"))
        return BilibiliVideo(
            aid=aid,
            bvid=bvid,
            title=str(data.get("title") or ""),
            description=str(data.get("desc") or data.get("description") or ""),
            url=f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            cover_url=str(data.get("pic") or data.get("cover") or ""),
            author_name=str(owner.get("name") or data.get("author") or ""),
            author_uid=str(owner.get("mid") or data.get("mid") or ""),
            timestamp=timestamp,
            metrics={
                key: _integer(stat.get(key) if stat else data.get(key))
                for key in ("view", "like", "reply", "coin")
            },
        )

    @staticmethod
    def _dynamic_from_api(
        data: Mapping[str, Any], fallback_uid: str = ""
    ) -> BilibiliEvent:
        modules = data.get("modules") if isinstance(data.get("modules"), dict) else {}
        author = modules.get("module_author") if isinstance(modules.get("module_author"), dict) else {}
        dynamic = modules.get("module_dynamic") if isinstance(modules.get("module_dynamic"), dict) else {}
        desc = dynamic.get("desc") if isinstance(dynamic.get("desc"), dict) else {}
        major = dynamic.get("major") if isinstance(dynamic.get("major"), dict) else {}
        archive = major.get("archive") if isinstance(major.get("archive"), dict) else {}
        draw = major.get("draw") if isinstance(major.get("draw"), dict) else {}
        draw_items = draw.get("items") if isinstance(draw.get("items"), list) else []
        covers = [
            str(item.get("src"))
            for item in draw_items
            if isinstance(item, dict) and item.get("src")
        ]
        if archive.get("cover"):
            covers.insert(0, str(archive["cover"]))
        event_id = str(data.get("id_str") or data.get("id") or "")
        if not event_id:
            raise BilibiliAPIError("Bilibili dynamic item did not contain an id")
        uid = str(author.get("mid") or fallback_uid)
        return BilibiliEvent(
            kind="dynamic",
            uid=uid,
            event_id=event_id,
            title=str(archive.get("title") or "动态更新"),
            body=str(desc.get("text") or ""),
            url=f"https://t.bilibili.com/{event_id}",
            author_name=str(author.get("name") or ""),
            avatar_url=str(author.get("face") or ""),
            cover_urls=covers,
            timestamp=_timestamp(author.get("pub_ts")),
        )


def _integer(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _timestamp(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError, OSError):
        return None
